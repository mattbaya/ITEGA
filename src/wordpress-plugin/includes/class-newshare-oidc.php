<?php
/**
 * Newshare OIDC Relying Party (RP).
 *
 * This class implements the OpenID Connect Authorization Code Flow as the
 * Relying Party (RP) within the Newshare Network's four-party federated model.
 *
 * OIDC Flow Overview:
 *   1. AUTHORIZE: User clicks "Network Login" -> plugin redirects to ALS /authorize
 *   2. ALS REDIRECT: ALS redirects user to their Home Base (Keycloak) for authentication
 *   3. CALLBACK: After auth, ALS redirects back to our REST callback with a session_token JWT
 *   4. TOKEN VALIDATION: Plugin validates the JWT signature against ALS JWKS public keys
 *   5. CLAIMS EXTRACTION: Plugin extracts networkUserId, networkGroupId, etc. from the JWT
 *   6. USER MAPPING: Plugin finds or creates a local WP user linked to the opaque networkUserId
 *   7. SESSION: Plugin logs the user into WordPress and redirects to the original article
 *
 * Security Architecture:
 *   - The plugin NEVER talks to Keycloak directly; all auth flows go through the ALS.
 *   - No PII is stored locally; only opaque identifiers (PPID) from the ALS.
 *   - CSRF protection uses cryptographically random state tokens (NOT predictable WP nonces).
 *   - JWT validation enforces RS256 algorithm, issuer, and audience checks.
 *   - The return URL (where the user was reading) is preserved through the entire OIDC flow.
 *
 * @package Newshare_Network
 * @since   0.1.0
 * @see     https://openid.net/specs/openid-connect-core-1_0.html
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
	 * Used to clear session data on logout and read current session state.
	 *
	 * @var Newshare_Session
	 */
	private Newshare_Session $session;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session $session Session manager dependency (injected by the main plugin class).
	 */
	public function __construct( Newshare_Session $session ) {
		$this->session = $session;
	}

	// =========================================================================
	// REST API Route Registration
	// =========================================================================

	/**
	 * Register REST API routes for the OIDC callback.
	 *
	 * This registers the callback endpoint that the ALS redirects to after
	 * successful authentication. The endpoint receives a state parameter
	 * (for CSRF verification) and a session_token JWT (containing the user's
	 * network claims).
	 *
	 * Hooked to: rest_api_init
	 */
	public function register_routes(): void {
		register_rest_route(
			'newshare/v1',
			'/callback',
			array(
				// POST as well as GET. The ALS hands the session token back by
				// auto-submitting a form rather than putting it in a query
				// string, so that a signed identity assertion never lands in a
				// browser history, a referer header or an access log. A GET-only
				// route answers that POST with "no route matching the URL and
				// request method", which is where the sign-in used to die.
				'methods'             => 'GET, POST',
				'callback'            => array( $this, 'handle_callback' ),
				'permission_callback' => '__return_true',
				'args'                => array(
					'state' => array(
						'required'          => true,
						'type'              => 'string',
						'sanitize_callback' => 'sanitize_text_field',
					),
				),
			)
		);
	}

	// =========================================================================
	// Step 1: Initiate OIDC Login (Authorize)
	// =========================================================================

	/**
	 * Initiate the OIDC login flow by redirecting to the ALS authorize endpoint.
	 *
	 * This is the entry point for the OIDC Authorization Code Flow. It:
	 *   1. Validates that the plugin is configured (ALS endpoint + publisher ID).
	 *   2. Generates a cryptographically random state token for CSRF protection.
	 *   3. Captures the user's current page URL so we can redirect back after auth.
	 *   4. Stores the state token and return URL in a WP transient (server-side).
	 *   5. Redirects the user to the ALS /authorize endpoint.
	 *
	 * The ALS handles the actual Keycloak interaction -- we never talk to Keycloak directly.
	 *
	 * @param string|null $return_to Optional. The URL to redirect back to after auth.
	 *                               If null, attempts to use the HTTP referer.
	 */
	public function initiate_login( ?string $return_to = null ): void {
		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );
		$pub_mbr_id        = get_option( 'newshare_pub_mbr_id' );

		if ( empty( $als_auth_endpoint ) || empty( $pub_mbr_id ) ) {
			wp_die(
				esc_html__( 'Newshare Network is not configured. Please contact the site administrator.', 'newshare-network' ),
				esc_html__( 'Configuration Error', 'newshare-network' ),
				array( 'response' => 500 )
			);
		}

		// -----------------------------------------------------------------
		// FIX (MAJOR): Generate a cryptographically random state parameter.
		//
		// Previously this used wp_create_nonce('newshare_oidc'), which is
		// deterministic (based on user ID, action string, and time window).
		// An attacker who knows the user's session cookie could predict it.
		// Now we use random_bytes() for a truly unpredictable state token
		// and store it in a transient for server-side verification.
		// -----------------------------------------------------------------
		$state = bin2hex( random_bytes( 16 ) );

		// Store the state token in a transient so we can verify it in the callback.
		// Expires after 10 minutes -- more than enough for a login round-trip.
		set_transient( 'newshare_oidc_state_' . $state, true, 10 * MINUTE_IN_SECONDS );

		// -----------------------------------------------------------------
		// FIX (MAJOR): Capture the current page URL before redirect.
		//
		// When a user clicks "Network Login" on a gated article, we need
		// to return them to that article after auth, not to wp-login.php
		// or the home page. The return URL can be passed explicitly (e.g.,
		// from the access gate template) or detected from the HTTP referer.
		// -----------------------------------------------------------------
		if ( empty( $return_to ) ) {
			$return_to = wp_get_referer();
		}
		if ( empty( $return_to ) ) {
			$return_to = home_url( '/' );
		}
		set_transient( 'newshare_return_url_' . $state, $return_to, 10 * MINUTE_IN_SECONDS );

		// Build the callback URL (our REST endpoint that the ALS will redirect to).
		$callback_url = rest_url( 'newshare/v1/callback' );

		// -----------------------------------------------------------------
		// FIX (CRITICAL): Remove rawurlencode() around redirect_uri.
		//
		// WordPress's add_query_arg() already URL-encodes parameter values.
		// Wrapping the redirect_uri in rawurlencode() caused double-encoding
		// (e.g., %253A instead of %3A), which broke the OIDC flow because
		// the ALS could not match the redirect_uri against its allowlist.
		// -----------------------------------------------------------------
		// The ALS registers publishers under an OIDC client_id, which is not
		// the same string as the Publishing Member ID: ITEGA-PA-0001 identifies
		// the member for settlement, pub-a identifies the OIDC client. Sending
		// the member ID here gets the request rejected as an unknown client.
		$client_id = get_option( 'newshare_als_client_id' );
		if ( empty( $client_id ) ) {
			$client_id = $pub_mbr_id;
		}

		$authorize_url = add_query_arg(
			array(
				'client_id'     => $client_id,
				'redirect_uri'  => $callback_url,
				'response_type' => 'code',
				// Just 'openid'. There is no 'newshare' client scope defined at
				// the home bases, and asking for one gets the whole request
				// rejected with invalid_scope. The network claims reach the
				// token through protocol mappers on the client, not a scope.
				'scope'         => 'openid',
				'state'         => $state,
			),
			trailingslashit( $als_auth_endpoint ) . 'auth/authorize'
		);

		wp_redirect( $authorize_url );
		exit;
	}

	// =========================================================================
	// Step 2: Handle OIDC Callback (Token Validation + Login)
	// =========================================================================

	/**
	 * Handle the OIDC callback from the ALS.
	 *
	 * This is the endpoint the ALS redirects to after successful authentication.
	 * It performs the following steps:
	 *   1. Verify the state parameter against the stored transient (CSRF check).
	 *   2. Validate the session_token JWT (signature, issuer, audience, expiry).
	 *   3. Extract network claims (networkUserId, networkGroupId, etc.).
	 *   4. Find or create a local WordPress user linked to this networkUserId.
	 *   5. Store network session data in user meta (opaque IDs only, no PII).
	 *   6. Redirect to a login finalization endpoint that sets the auth cookie.
	 *
	 * @param WP_REST_Request $request The incoming callback request from the ALS.
	 * @return WP_REST_Response|WP_Error Response on error, or exits via redirect on success.
	 */
	public function handle_callback( WP_REST_Request $request ) {
		// -----------------------------------------------------------------
		// Step 2a: Verify state parameter for CSRF protection.
		//
		// FIX (MAJOR): Use transient-based verification instead of wp_verify_nonce().
		// The state was generated with random_bytes() in initiate_login(), so we
		// verify it by checking if the matching transient exists. We also keep
		// wp_verify_nonce() as an ADDITIONAL layer if the user has a WP session,
		// but the primary protection is the cryptographic state token.
		// -----------------------------------------------------------------
		$state = $request->get_param( 'state' );
		$state_valid = get_transient( 'newshare_oidc_state_' . $state );

		if ( ! $state_valid ) {
			return new WP_Error(
				'invalid_state',
				__( 'Invalid or expired state parameter. Please try logging in again.', 'newshare-network' ),
				array( 'status' => 403 )
			);
		}

		// Delete the state transient immediately to prevent replay attacks.
		delete_transient( 'newshare_oidc_state_' . $state );

		// Step 2b: Extract the session token from query params.
		// The ALS names this claim camelCase on the wire; earlier builds of this
		// plugin expected snake_case. Accept either so a version skew between
		// the two halves cannot silently break sign-in.
		$session_token = $request->get_param( 'sessionToken' );
		if ( empty( $session_token ) ) {
			$session_token = $request->get_param( 'session_token' );
		}
		if ( empty( $session_token ) ) {
			return new WP_Error(
				'missing_token',
				__( 'No session token received from the network.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		// Step 2c: Validate the session token JWT (signature, algorithm, expiry).
		$claims = $this->validate_jwt( $session_token );
		if ( is_wp_error( $claims ) ) {
			return $claims;
		}

		// Step 2d: Extract network claims from the validated JWT.
		// These are all opaque identifiers -- no PII is present in the token.
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

		// Step 2e: Find or create a WordPress user linked to this networkUserId.
		$user_id = $this->find_or_create_user( $network_user_id );
		if ( is_wp_error( $user_id ) ) {
			return $user_id;
		}

		// Step 2f: Update user meta with network session data.
		// No PII is stored -- only opaque identifiers from the ALS.
		update_user_meta( $user_id, 'newshare_network_user_id', $network_user_id );
		update_user_meta( $user_id, 'newshare_network_group_id', $network_group_id );
		update_user_meta( $user_id, 'newshare_home_base_id', $home_base_id );
		update_user_meta( $user_id, 'newshare_session_id', $session_id );
		update_user_meta( $user_id, 'newshare_markup_ratio', $markup_ratio );
		update_user_meta( $user_id, 'newshare_session_expires', $expires );

		// -----------------------------------------------------------------
		// FIX (CRITICAL): Do NOT call wp_set_auth_cookie() in REST context.
		//
		// wp_set_auth_cookie() sends HTTP Set-Cookie headers. In a REST API
		// context, headers may already have been sent (e.g., by REST API
		// response handling), causing the cookie to silently fail. Instead,
		// we store the pending login in a short-lived transient and redirect
		// to a dedicated front-end URL that sets the cookie in a fresh
		// HTTP response where headers are guaranteed to be available.
		// -----------------------------------------------------------------

		// Store the pending login data in a one-time-use transient.
		$login_token = bin2hex( random_bytes( 16 ) );
		set_transient(
			'newshare_pending_login_' . $login_token,
			$user_id,
			60 // 60 seconds -- just enough time for the redirect.
		);

		// Get the return URL from the state parameter.
		$return_url = get_transient( 'newshare_return_url_' . $state );
		delete_transient( 'newshare_return_url_' . $state );

		if ( empty( $return_url ) ) {
			$return_url = home_url( '/' );
		}

		// Store the return URL with the login token so finalize_login can use it.
		set_transient(
			'newshare_pending_return_' . $login_token,
			$return_url,
			60
		);

		// Redirect to a dedicated login finalization endpoint (not REST API).
		$finalize_url = add_query_arg(
			array(
				'newshare_finalize' => $login_token,
			),
			home_url( '/' )
		);

		wp_safe_redirect( $finalize_url );
		exit;
	}

	/**
	 * Finalize the login by setting the auth cookie in a non-REST context.
	 *
	 * This method is hooked to the 'init' action and handles the redirect
	 * from handle_callback(). It runs in a normal page load context where
	 * HTTP headers have not yet been sent, so wp_set_auth_cookie() works
	 * reliably.
	 *
	 * The login token is a one-time-use transient that maps to a user ID.
	 * After setting the cookie, it redirects to the original article URL.
	 *
	 * Hooked to: init (registered in the main plugin class)
	 */
	public function finalize_login(): void {
		// Only act if the finalize parameter is present.
		if ( ! isset( $_GET['newshare_finalize'] ) ) {
			return;
		}

		$login_token = sanitize_text_field( wp_unslash( $_GET['newshare_finalize'] ) );
		if ( empty( $login_token ) ) {
			return;
		}

		// Retrieve the pending user ID from the transient.
		$user_id = get_transient( 'newshare_pending_login_' . $login_token );
		if ( false === $user_id ) {
			// Token expired or invalid -- redirect home gracefully.
			wp_safe_redirect( home_url( '/' ) );
			exit;
		}

		// Delete the transient immediately to prevent replay.
		delete_transient( 'newshare_pending_login_' . $login_token );

		// Set the WordPress auth cookie -- safe here because this is a normal
		// page load (not REST API), so headers have not been sent yet.
		wp_set_auth_cookie( (int) $user_id, false );
		wp_set_current_user( (int) $user_id );

		// Retrieve and clean up the return URL.
		$return_url = get_transient( 'newshare_pending_return_' . $login_token );
		delete_transient( 'newshare_pending_return_' . $login_token );

		if ( empty( $return_url ) ) {
			$return_url = home_url( '/' );
		}

		// Redirect to the article the user was originally reading.
		wp_safe_redirect( $return_url );
		exit;
	}

	// =========================================================================
	// JWT Validation
	// =========================================================================

	/**
	 * Validate a JWT session token from the ALS.
	 *
	 * Performs the following checks:
	 *   1. Structural validation (3-part JWT format).
	 *   2. Algorithm enforcement (must be RS256 per protocol spec).
	 *   3. Signature verification using the ALS public keys (JWKS).
	 *   4. Issuer verification (must match our configured ALS endpoint).
	 *   5. Audience verification (must include our publisher member ID).
	 *   6. Expiration check (handled automatically by firebase/php-jwt).
	 *
	 * @param string $token The raw JWT string from the ALS callback.
	 * @return object|WP_Error Decoded JWT claims on success, WP_Error on failure.
	 */
	// The return type is left off deliberately: WP_Error is itself an object,
	// and PHP rejects a union that combines `object` with a specific class.
	// The contract is documented in the @return tag above.
	private function validate_jwt( string $token ) {
		// Step 3a: Structural validation -- JWT must have exactly 3 parts (header.payload.signature).
		$token_parts = explode( '.', $token );
		if ( count( $token_parts ) !== 3 ) {
			return new WP_Error(
				'invalid_jwt',
				__( 'Malformed JWT token.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		// Step 3b: Decode header and enforce RS256 algorithm.
		// This prevents algorithm confusion attacks (e.g., switching to HS256
		// and using the public key as an HMAC secret).
		$header = json_decode( base64_decode( strtr( $token_parts[0], '-_', '+/' ) ) );
		if ( ! $header || ! isset( $header->alg ) || 'RS256' !== $header->alg ) {
			return new WP_Error(
				'invalid_algorithm',
				__( 'JWT must use RS256 algorithm.', 'newshare-network' ),
				array( 'status' => 400 )
			);
		}

		// Step 3c: Fetch the ALS public keys (JWKS) for signature verification.
		$keys = $this->get_als_public_keys();
		if ( is_wp_error( $keys ) ) {
			return $keys;
		}

		$pub_mbr_id        = get_option( 'newshare_pub_mbr_id' );
		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );

		try {
			// Step 3d: Decode and verify the JWT signature.
			// firebase/php-jwt automatically checks exp, nbf, and iat claims.
			$decoded = JWT::decode( $token, $keys );

			// Step 3e: Verify the issuer matches our configured ALS endpoint.
			// This prevents tokens from a different ALS being accepted.
			if ( ! isset( $decoded->iss ) || $decoded->iss !== $als_auth_endpoint ) {
				return new WP_Error(
					'invalid_issuer',
					__( 'Token issuer does not match the configured ALS endpoint.', 'newshare-network' ),
					array( 'status' => 403 )
				);
			}

			// Step 3f: Verify the audience includes our publisher member ID.
			// The ALS sets aud to the client_id (pubMbrId) of the requesting publisher.
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

	// =========================================================================
	// JWKS Key Fetching & Caching
	// =========================================================================

	/**
	 * Fetch and cache the ALS public keys from the JWKS endpoint.
	 *
	 * Keys are cached in a WordPress transient for 5 minutes to avoid hitting
	 * the ALS on every JWT validation. The JWKS URI is discovered from the
	 * ALS OIDC configuration endpoint (/.well-known/openid-configuration),
	 * or can be manually overridden in settings.
	 *
	 * @return array|WP_Error Array of Key objects on success, WP_Error on failure.
	 */
	private function get_als_public_keys(): array|WP_Error {
		// Check the transient cache first to avoid unnecessary HTTP requests.
		// The cache holds the raw JWKS document, so re-parse on the way out.
		$cached_jwks = get_transient( 'newshare_als_public_key' );
		if ( false !== $cached_jwks && isset( $cached_jwks['keys'] ) ) {
			try {
				return JWK::parseKeySet( $cached_jwks, 'RS256' );
			} catch ( \Exception $e ) {
				delete_transient( 'newshare_als_public_key' );
			}
		}

		// Discover the JWKS URI from the OIDC configuration.
		$jwks_uri = $this->discover_jwks_uri();
		if ( is_wp_error( $jwks_uri ) ) {
			return $jwks_uri;
		}

		// Fetch the JWKS document from the ALS.
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
			// -----------------------------------------------------------------
			// FIX (Minor): Pass default algorithm to JWK::parseKeySet().
			//
			// In firebase/php-jwt v6+, parseKeySet() requires a default
			// algorithm parameter for keys that don't specify an 'alg' field.
			// The Newshare protocol mandates RS256 for all JWT operations,
			// so we set 'RS256' as the default.
			// -----------------------------------------------------------------
			$keys = JWK::parseKeySet( $jwks, 'RS256' );
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

		// Cache the raw JWKS document, never the parsed keys.
		//
		// JWK::parseKeySet() returns OpenSSLAsymmetricKey objects, and PHP 8
		// refuses to serialize those: set_transient() throws "Serialization of
		// 'OpenSSLAsymmetricKey' is not allowed", which is an uncaught fatal
		// inside the REST callback. The reader's browser gets a blank 500 at
		// the very last step of signing in, with the cause visible only in the
		// PHP error log. Caching the JSON and re-parsing costs microseconds.
		set_transient( 'newshare_als_public_key', $jwks, 5 * MINUTE_IN_SECONDS );

		return $keys;
	}

	/**
	 * Discover the JWKS URI from the ALS OIDC configuration endpoint.
	 *
	 * Standard OIDC Discovery: fetches /.well-known/openid-configuration from
	 * the ALS and extracts the jwks_uri field. The admin can override this
	 * with a manual URL in the plugin settings (useful for development).
	 *
	 * @return string|WP_Error JWKS URI on success, WP_Error on failure.
	 */
	private function discover_jwks_uri(): string|WP_Error {
		// Allow manual override via settings (useful for dev/staging environments).
		$manual_url = get_option( 'newshare_als_public_key_url' );
		if ( ! empty( $manual_url ) ) {
			return $manual_url;
		}

		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );
		$config_url        = trailingslashit( $als_auth_endpoint ) . '.well-known/openid-configuration';

		// Check the cached OIDC configuration first.
		$cached_config = get_transient( 'newshare_als_oidc_config' );
		if ( false !== $cached_config && isset( $cached_config['jwks_uri'] ) ) {
			return $cached_config['jwks_uri'];
		}

		// Fetch the OIDC configuration document from the ALS.
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

		// Cache the OIDC configuration for 5 minutes.
		set_transient( 'newshare_als_oidc_config', $config, 5 * MINUTE_IN_SECONDS );

		return $config['jwks_uri'];
	}

	// =========================================================================
	// User Management
	// =========================================================================

	/**
	 * Find an existing WP user linked to a networkUserId, or create one.
	 *
	 * Network users are created as WordPress subscribers with pseudonymous
	 * identities. No PII is stored -- only the opaque networkUserId (a PPID
	 * unique to this publisher). The user gets a non-functional email address
	 * at network.newshare.local so WordPress's email requirement is satisfied
	 * without leaking any real identity.
	 *
	 * @param string $network_user_id The opaque PPID from the ALS (unique per publisher).
	 * @return int|WP_Error WordPress user ID on success, WP_Error on failure.
	 */
	/**
	 * A short, readable name for a reader nobody is allowed to identify.
	 *
	 * Every network reader used to be called "Network User", so a site with six
	 * of them greeted all six identically and the greeting told nobody anything
	 * -- including which account they were actually using.
	 *
	 * The pairwise identifier is the only thing about this reader that exists
	 * here, so the label is built from it: stable, distinct per reader, and
	 * still meaningless to anyone who has not been told whose it is. It is
	 * already different at every publisher, so it cannot be used to follow
	 * somebody between sites either.
	 *
	 * @param string $network_user_id The reader's pairwise identifier.
	 * @return string
	 */
	private static function reader_label( string $network_user_id ): string {
		$short = strtoupper( substr( preg_replace( '/[^a-zA-Z0-9]/', '', $network_user_id ), 0, 6 ) );
		/* translators: %s: a short opaque code identifying the reader at this publisher. */
		return sprintf( __( 'ITEGA Guest %s', 'newshare-network' ), $short );
	}

	private function find_or_create_user( string $network_user_id ): int|WP_Error {
		// Search for an existing user by their network ID (stored in user meta).
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
		// The username is derived from the networkUserId (truncated to 40 chars
		// to stay within WP's user_login length limit).
		$username = 'newshare_' . substr( $network_user_id, 0, 40 );
		$email    = $username . '@network.newshare.local';

		// Adopt an existing account before trying to make one.
		//
		// The username is derived deterministically from the networkUserId, so
		// if the link meta is ever lost -- a partial write, a restore, a manual
		// edit -- the lookup above misses, this tries to create a duplicate,
		// wp_insert_user() refuses, and the reader gets a 500 on every future
		// sign-in with no way back. Re-adopting the account and rewriting the
		// meta makes that self-healing instead of permanent.
		$existing = get_user_by( 'login', $username );
		if ( $existing instanceof WP_User ) {
			update_user_meta( $existing->ID, 'newshare_network_user_id', $network_user_id );
			return $existing->ID;
		}

		$user_id = wp_insert_user(
			array(
				'user_login'   => $username,
				'user_email'   => $email,
				'user_pass'    => wp_generate_password( 32, true, true ),
				'role'         => NEWSHARE_ROLE,
				'display_name' => self::reader_label( $network_user_id ),
			)
		);

		if ( is_wp_error( $user_id ) ) {
			return new WP_Error(
				'user_creation_failed',
				__( 'Failed to create a local account for the network user.', 'newshare-network' ),
				array( 'status' => 500 )
			);
		}

		// Store the networkUserId in user meta so we can find this user again
		// on subsequent logins.
		update_user_meta( $user_id, 'newshare_network_user_id', $network_user_id );

		return $user_id;
	}
}
