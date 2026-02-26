<?php
/**
 * Newshare OIDC Relying Party.
 *
 * Handles the OpenID Connect authorization code flow through the ALS.
 * The flow goes: Plugin -> ALS -> Keycloak -> ALS -> Plugin callback.
 * The plugin never talks to Keycloak directly.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

use Firebase\JWT\JWT;
use Firebase\JWT\JWK;
use Firebase\JWT\Key;

class Newshare_OIDC {

	/**
	 * Session manager instance.
	 *
	 * @var Newshare_Session
	 */
	private Newshare_Session $session;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session $session Session manager.
	 */
	public function __construct( Newshare_Session $session ) {
		$this->session = $session;
	}

	/**
	 * Register REST API routes for the OIDC callback.
	 */
	public function register_routes(): void {
		register_rest_route(
			'newshare/v1',
			'/callback',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'handle_callback' ),
				'permission_callback' => '__return_true',
				'args'                => array(
					'state' => array(
						'required'          => true,
						'type'              => 'string',
						'sanitize_callback' => 'sanitize_text_field',
					),
					'session_token' => array(
						'required'          => true,
						'type'              => 'string',
						'sanitize_callback' => 'sanitize_text_field',
					),
				),
			)
		);
	}

	/**
	 * Initiate the OIDC login flow.
	 *
	 * Redirects the user to the ALS authorize endpoint. The ALS handles
	 * the actual Keycloak interaction — we never talk to Keycloak directly.
	 */
	public function initiate_login(): void {
		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );
		$pub_mbr_id        = get_option( 'newshare_pub_mbr_id' );

		if ( empty( $als_auth_endpoint ) || empty( $pub_mbr_id ) ) {
			wp_die(
				esc_html__( 'Newshare Network is not configured. Please contact the site administrator.', 'newshare-network' ),
				esc_html__( 'Configuration Error', 'newshare-network' ),
				array( 'response' => 500 )
			);
		}

		// Generate state nonce for CSRF protection.
		$state = wp_create_nonce( 'newshare_oidc' );

		// Store the originally-requested URL so we can redirect back after auth.
		$return_url = wp_get_referer();
		if ( empty( $return_url ) ) {
			$return_url = home_url( '/' );
		}
		set_transient( 'newshare_return_url_' . $state, $return_url, 10 * MINUTE_IN_SECONDS );

		// Build the callback URL (our REST endpoint).
		$callback_url = rest_url( 'newshare/v1/callback' );

		// Build the ALS authorize URL.
		$authorize_url = add_query_arg(
			array(
				'client_id'     => $pub_mbr_id,
				'redirect_uri'  => rawurlencode( $callback_url ),
				'response_type' => 'code',
				'scope'         => 'openid newshare',
				'state'         => $state,
			),
			trailingslashit( $als_auth_endpoint ) . 'authorize'
		);

		wp_redirect( $authorize_url );
		exit;
	}

	/**
	 * Handle the OIDC callback from the ALS.
	 *
	 * Validates the session token JWT, extracts claims, finds or creates
	 * a WordPress user, and logs them in.
	 *
	 * @param WP_REST_Request $request The incoming callback request.
	 * @return WP_REST_Response|WP_Error
	 */
	public function handle_callback( WP_REST_Request $request ) {
		// 1. Verify state nonce for CSRF protection.
		$state = $request->get_param( 'state' );
		if ( ! wp_verify_nonce( $state, 'newshare_oidc' ) ) {
			return new WP_Error(
				'invalid_state',
				__( 'Invalid or expired state parameter. Please try logging in again.', 'newshare-network' ),
				array( 'status' => 403 )
			);
		}

		// 2. Get the session token from query params.
		$session_token = $request->get_param( 'session_token' );
		if ( empty( $session_token ) ) {
			return new WP_Error(
				'missing_token',
				__( 'No session token received from the network.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		// 3. Validate the session token JWT.
		$claims = $this->validate_jwt( $session_token );
		if ( is_wp_error( $claims ) ) {
			return $claims;
		}

		// 4. Extract claims.
		$network_user_id  = sanitize_text_field( $claims->networkUserId ?? '' );
		$network_group_id = absint( $claims->networkGroupId ?? 0 );
		$home_base_id     = sanitize_text_field( $claims->homeBaseId ?? '' );
		$pub_mbr_id       = sanitize_text_field( $claims->pubMbrId ?? '' );
		$session_id       = sanitize_text_field( $claims->sessionId ?? '' );
		$markup_ratio     = floatval( $claims->markupRatio ?? 1.0 );
		$expires          = absint( $claims->exp ?? 0 );

		if ( empty( $network_user_id ) ) {
			return new WP_Error(
				'missing_claims',
				__( 'Session token is missing required claims.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		// 5. Find or create a WordPress user linked to this networkUserId.
		$user_id = $this->find_or_create_user( $network_user_id );
		if ( is_wp_error( $user_id ) ) {
			return $user_id;
		}

		// 6. Update user meta with network session data.
		// No PII is stored — only opaque identifiers.
		update_user_meta( $user_id, 'newshare_network_user_id', $network_user_id );
		update_user_meta( $user_id, 'newshare_network_group_id', $network_group_id );
		update_user_meta( $user_id, 'newshare_home_base_id', $home_base_id );
		update_user_meta( $user_id, 'newshare_session_id', $session_id );
		update_user_meta( $user_id, 'newshare_markup_ratio', $markup_ratio );
		update_user_meta( $user_id, 'newshare_session_expires', $expires );

		// 7. Log the user into WordPress.
		wp_set_auth_cookie( $user_id, false );
		wp_set_current_user( $user_id );

		// 8. Redirect to the originally-requested URL.
		$return_url = get_transient( 'newshare_return_url_' . $state );
		delete_transient( 'newshare_return_url_' . $state );

		if ( empty( $return_url ) ) {
			$return_url = home_url( '/' );
		}

		wp_safe_redirect( $return_url );
		exit;
	}

	/**
	 * Validate a JWT session token from the ALS.
	 *
	 * @param string $token The raw JWT string.
	 * @return object|WP_Error Decoded claims on success, WP_Error on failure.
	 */
	private function validate_jwt( string $token ): object|WP_Error {
		// Decode the header to verify algorithm.
		$token_parts = explode( '.', $token );
		if ( count( $token_parts ) !== 3 ) {
			return new WP_Error(
				'invalid_jwt',
				__( 'Malformed JWT token.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		$header = json_decode( base64_decode( strtr( $token_parts[0], '-_', '+/' ) ) );
		if ( ! $header || ! isset( $header->alg ) || 'RS256' !== $header->alg ) {
			return new WP_Error(
				'invalid_algorithm',
				__( 'JWT must use RS256 algorithm.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		// Fetch the ALS public keys.
		$keys = $this->get_als_public_keys();
		if ( is_wp_error( $keys ) ) {
			return $keys;
		}

		$pub_mbr_id        = get_option( 'newshare_pub_mbr_id' );
		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );

		try {
			$decoded = JWT::decode( $token, $keys );

			// Verify issuer matches the ALS.
			if ( ! isset( $decoded->iss ) || $decoded->iss !== $als_auth_endpoint ) {
				return new WP_Error(
					'invalid_issuer',
					__( 'Token issuer does not match the configured ALS endpoint.', 'newshare-network' ),
					array( 'status' => 403 )
				);
			}

			// Verify audience matches our publisher ID.
			$audience = is_array( $decoded->aud ) ? $decoded->aud : array( $decoded->aud );
			if ( ! in_array( $pub_mbr_id, $audience, true ) ) {
				return new WP_Error(
					'invalid_audience',
					__( 'Token audience does not match this publisher.', 'newshare-network' ),
					array( 'status' => 403 )
				);
			}

			return $decoded;
		} catch ( \Exception $e ) {
			return new WP_Error(
				'jwt_validation_failed',
				sprintf(
					/* translators: %s: error message from JWT library */
					__( 'JWT validation failed: %s', 'newshare-network' ),
					$e->getMessage()
				),
				array( 'status' => 403 )
			);
		}
	}

	/**
	 * Fetch and cache the ALS public keys from the JWKS endpoint.
	 *
	 * Keys are cached in a transient for 5 minutes to avoid hitting the
	 * ALS on every request.
	 *
	 * @return array|WP_Error Array of Key objects on success, WP_Error on failure.
	 */
	private function get_als_public_keys(): array|WP_Error {
		$cached_keys = get_transient( 'newshare_als_public_key' );
		if ( false !== $cached_keys ) {
			return $cached_keys;
		}

		// Discover the JWKS URI from the OIDC configuration.
		$jwks_uri = $this->discover_jwks_uri();
		if ( is_wp_error( $jwks_uri ) ) {
			return $jwks_uri;
		}

		// Fetch the JWKS.
		$response = wp_remote_get(
			$jwks_uri,
			array(
				'timeout' => 10,
				'headers' => array( 'Accept' => 'application/json' ),
			)
		);

		if ( is_wp_error( $response ) ) {
			return new WP_Error(
				'jwks_fetch_failed',
				__( 'Failed to fetch ALS public keys.', 'newshare-network' ),
				array( 'status' => 502 )
			);
		}

		$status_code = wp_remote_retrieve_response_code( $response );
		if ( 200 !== $status_code ) {
			return new WP_Error(
				'jwks_fetch_failed',
				sprintf(
					/* translators: %d: HTTP status code */
					__( 'ALS JWKS endpoint returned HTTP %d.', 'newshare-network' ),
					$status_code
				),
				array( 'status' => 502 )
			);
		}

		$body = wp_remote_retrieve_body( $response );
		$jwks = json_decode( $body, true );

		if ( ! $jwks || ! isset( $jwks['keys'] ) ) {
			return new WP_Error(
				'jwks_parse_failed',
				__( 'Failed to parse ALS JWKS response.', 'newshare-network' ),
				array( 'status' => 502 )
			);
		}

		try {
			$keys = JWK::parseKeySet( $jwks );
		} catch ( \Exception $e ) {
			return new WP_Error(
				'jwks_parse_failed',
				sprintf(
					/* translators: %s: error message */
					__( 'Failed to parse JWKS key set: %s', 'newshare-network' ),
					$e->getMessage()
				),
				array( 'status' => 502 )
			);
		}

		// Cache for 5 minutes.
		set_transient( 'newshare_als_public_key', $keys, 5 * MINUTE_IN_SECONDS );

		return $keys;
	}

	/**
	 * Discover the JWKS URI from the ALS OIDC configuration endpoint.
	 *
	 * @return string|WP_Error JWKS URI on success, WP_Error on failure.
	 */
	private function discover_jwks_uri(): string|WP_Error {
		// Allow manual override via settings.
		$manual_url = get_option( 'newshare_als_public_key_url' );
		if ( ! empty( $manual_url ) ) {
			return $manual_url;
		}

		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );
		$config_url        = trailingslashit( $als_auth_endpoint ) . '.well-known/openid-configuration';

		// Check cache.
		$cached_config = get_transient( 'newshare_als_oidc_config' );
		if ( false !== $cached_config && isset( $cached_config['jwks_uri'] ) ) {
			return $cached_config['jwks_uri'];
		}

		$response = wp_remote_get(
			$config_url,
			array(
				'timeout' => 10,
				'headers' => array( 'Accept' => 'application/json' ),
			)
		);

		if ( is_wp_error( $response ) ) {
			return new WP_Error(
				'oidc_discovery_failed',
				__( 'Failed to fetch ALS OIDC configuration.', 'newshare-network' ),
				array( 'status' => 502 )
			);
		}

		$body   = wp_remote_retrieve_body( $response );
		$config = json_decode( $body, true );

		if ( ! $config || ! isset( $config['jwks_uri'] ) ) {
			return new WP_Error(
				'oidc_discovery_failed',
				__( 'ALS OIDC configuration does not contain a jwks_uri.', 'newshare-network' ),
				array( 'status' => 502 )
			);
		}

		set_transient( 'newshare_als_oidc_config', $config, 5 * MINUTE_IN_SECONDS );

		return $config['jwks_uri'];
	}

	/**
	 * Find an existing WP user linked to a networkUserId, or create one.
	 *
	 * Network users are created as subscribers with no PII — only the
	 * opaque networkUserId is stored.
	 *
	 * @param string $network_user_id The opaque network user identifier.
	 * @return int|WP_Error WordPress user ID on success, WP_Error on failure.
	 */
	private function find_or_create_user( string $network_user_id ): int|WP_Error {
		// Search for existing user by network ID.
		$users = get_users(
			array(
				'meta_key'   => 'newshare_network_user_id',
				'meta_value' => $network_user_id,
				'number'     => 1,
				'fields'     => 'ID',
			)
		);

		if ( ! empty( $users ) ) {
			return (int) $users[0];
		}

		// Create a new WP user with a pseudonymous username.
		$username = 'newshare_' . substr( $network_user_id, 0, 40 );
		$email    = $username . '@network.newshare.local';

		$user_id = wp_insert_user(
			array(
				'user_login' => $username,
				'user_email' => $email,
				'user_pass'  => wp_generate_password( 32, true, true ),
				'role'       => 'subscriber',
				'display_name' => __( 'Network User', 'newshare-network' ),
			)
		);

		if ( is_wp_error( $user_id ) ) {
			return new WP_Error(
				'user_creation_failed',
				__( 'Failed to create a local account for the network user.', 'newshare-network' ),
				array( 'status' => 500 )
			);
		}

		update_user_meta( $user_id, 'newshare_network_user_id', $network_user_id );

		return $user_id;
	}
}
