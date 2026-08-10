<?php
/**
 * Newshare AI Agent Handshake.
 *
 * Handles machine callers -- AI answer engines crawling or retrieving content
 * for RAG -- which cannot be handled like readers. An engine has no browser,
 * cannot follow a redirect, and never logs in. It identifies itself on every
 * request, agrees a price machine-to-machine, and then crawls under a grant
 * until that grant expires.
 *
 * == The exchange ==
 *
 *   1. Engine requests an article, presenting its ITEGA member credentials.
 *   2. We ask the Authenticator whether it is a member in good standing and
 *      what business rules it agreed to.
 *   3. Not a member -> 403 with a note pointing at how to join. The refusal is
 *      deliberately useful rather than a bare denial.
 *   4. A member with no grant -> 402 Payment Required, stating our price.
 *   5. The engine re-sends carrying its acceptance; we record the agreement
 *      with the Authenticator and serve the content.
 *   6. Later requests presenting a valid grant are served immediately, with no
 *      handshake, until the grant times out. Each one is still logged and
 *      billed on its own -- the grant removes the negotiation, not the meter.
 *
 * == Why 402 and headers ==
 *
 * This is ITEGA's own protocol, but shaped like x402 on purpose. x402 covers
 * agentic payments and is heading for standardisation; expressing the price
 * agreement as a 402 exchange means adopting it later is a substitution rather
 * than a redesign. (x402 does not cover membership or identity, which is the
 * part steps 2-3 above are doing, and has no equivalent for it today.)
 *
 * @package Newshare_Network
 * @since   0.3.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_AI_Agent {

	/** Header carrying the agent's ITEGA member id. */
	private const HDR_AGENT_ID = 'HTTP_X_ITEGA_AGENT_ID';

	/** Header carrying the agent's member key. */
	private const HDR_AGENT_KEY = 'HTTP_X_ITEGA_AGENT_KEY';

	/** Header by which an agent presents an existing crawl grant. */
	private const HDR_GRANT = 'HTTP_X_ITEGA_GRANT';

	/** Header by which an agent accepts a quoted price. */
	private const HDR_ACCEPT_PRICE = 'HTTP_X_ITEGA_ACCEPT_PRICE';

	/** Seconds to wait on the Authenticator. Machine callers, so keep it tight. */
	private const TIMEOUT = 5;

	/**
	 * Logger, for filing a report on every fulfilled request.
	 *
	 * @var Newshare_Logger
	 */
	private Newshare_Logger $logger;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Logger $logger Event logger.
	 */
	public function __construct( Newshare_Logger $logger ) {
		$this->logger = $logger;
	}

	/**
	 * Whether the current request presents AI agent credentials.
	 *
	 * @return bool
	 */
	public function is_agent_request(): bool {
		return ! empty( $_SERVER[ self::HDR_AGENT_ID ] ) && ! empty( $_SERVER[ self::HDR_AGENT_KEY ] );
	}

	/**
	 * Handle a machine request for a piece of content.
	 *
	 * Called early, before the normal reader access gate: an engine must never
	 * fall through to a login prompt it cannot act on.
	 *
	 * Sends its own response and exits when the request cannot be served as-is.
	 * Returns true when the caller may serve the content.
	 *
	 * @param int $post_id The requested post.
	 * @return bool True if content should be served.
	 */
	public function handle( int $post_id ): bool {
		$agent_id  = $this->header( self::HDR_AGENT_ID );
		$agent_key = $this->header( self::HDR_AGENT_KEY );
		$grant     = $this->header( self::HDR_GRANT );
		$price     = $this->price_for( $post_id );
		$pub_mbr   = (string) get_option( 'newshare_pub_mbr_id', '' );

		// --- Already crawling under a grant? Serve without a handshake. ---
		if ( '' !== $grant ) {
			$checked = $this->post_to_als(
				'/ai-agent/grant/check',
				array( 'grant' => $grant, 'pubMbrId' => $pub_mbr )
			);
			if ( is_array( $checked ) && ! empty( $checked['valid'] ) ) {
				$this->log_agent_access( $post_id, $checked['agentMbrId'], (float) $checked['agreedPrice'] );
				return true;
			}
			// Expired or belongs to another publisher. Fall through to a fresh
			// handshake rather than refusing -- an expired grant is the normal
			// end of a crawl session, not an error.
		}

		// --- Is this a member in good standing? ---
		$verified = $this->post_to_als(
			'/ai-agent/verify',
			array(
				'agentMbrId' => $agent_id,
				'apiKey'     => $agent_key,
				'pubMbrId'   => $pub_mbr,
				'resourceId' => get_permalink( $post_id ),
			)
		);

		if ( ! is_array( $verified ) ) {
			$this->respond( 503, array( 'error' => 'ITEGA Authenticator unavailable.' ) );
		}

		if ( empty( $verified['member'] ) ) {
			// Point them somewhere. A crawler told only "no" learns nothing;
			// one told where to join might become a paying member.
			$this->respond(
				403,
				array(
					'error'     => (string) ( $verified['reason'] ?? 'Not an ITEGA member.' ),
					'joinAt'    => (string) ( $verified['signupUrl'] ?? '' ),
					'publisher' => $pub_mbr,
				)
			);
		}

		// --- Has the engine accepted our price on this request? ---
		$accepted = $this->header( self::HDR_ACCEPT_PRICE );
		if ( '' === $accepted ) {
			// No. Quote it and let it decide.
			$this->respond(
				402,
				array(
					'resource'       => get_permalink( $post_id ),
					'wholesalePrice' => $price,
					'currency'       => 'USD',
					'terms'          => 'per-resource',
					'acceptWith'     => 'X-ITEGA-Accept-Price',
				),
				array(
					'X-ITEGA-Price'    => (string) $price,
					'X-ITEGA-Resource' => get_permalink( $post_id ),
				)
			);
		}

		// Accepting a different number than we quoted is not an agreement.
		// Compared with a small tolerance because the value round-trips as a
		// decimal string through an HTTP header.
		if ( abs( (float) $accepted - $price ) > 0.00001 ) {
			$this->respond(
				409,
				array(
					'error'          => 'Accepted price does not match the quoted price.',
					'wholesalePrice' => $price,
				)
			);
		}

		// --- Agreed. Record it and serve. ---
		$granted = $this->post_to_als(
			'/ai-agent/grant',
			array(
				'agentMbrId'  => $agent_id,
				'apiKey'      => $agent_key,
				'pubMbrId'    => $pub_mbr,
				'agreedPrice' => $price,
			)
		);

		if ( ! is_array( $granted ) || empty( $granted['grant'] ) ) {
			$this->respond( 503, array( 'error' => 'Could not record the agreement.' ) );
		}

		$this->log_agent_access( $post_id, $agent_id, $price );

		// Hand back the grant so the engine can crawl on without renegotiating.
		header( 'X-ITEGA-Grant: ' . $granted['grant'] );
		header( 'X-ITEGA-Grant-Expires: ' . (string) ( $granted['expiresAt'] ?? '' ) );
		header( 'X-ITEGA-Price: ' . (string) $price );

		$this->allow_content();
		return true;
	}

	/**
	 * Clear this request past the reader access gate.
	 *
	 * The gate exists to stop unauthorised readers, and it decides using a
	 * subscription tier a machine caller does not have. An agent that has paid
	 * would otherwise be served a login prompt instead of the article it just
	 * agreed to buy.
	 */
	private function allow_content(): void {
		add_filter( 'newshare_bypass_access_gate', '__return_true' );
	}

	/**
	 * File a log report for a fulfilled machine request.
	 *
	 * Every request is reported individually even while a grant is open, so
	 * settlement bills per resource served rather than per handshake.
	 *
	 * @param int    $post_id  Resource served.
	 * @param string $agent_id The agent's ITEGA member id.
	 * @param float  $price    Wholesale price agreed.
	 */
	private function log_agent_access( int $post_id, string $agent_id, float $price ): void {
		$this->logger->log_ai_agent_access( $post_id, $agent_id, $price );
	}

	/**
	 * This publisher's asking price for a post.
	 *
	 * @param int $post_id Post to price.
	 * @return float Wholesale price.
	 */
	private function price_for( int $post_id ): float {
		$page_class = get_post_meta( $post_id, 'newshare_page_class', true );
		if ( '' === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}
		return (float) $page_class;
	}

	/**
	 * Read a request header, or '' when absent.
	 *
	 * @param string $key A HTTP_* key from $_SERVER.
	 * @return string
	 */
	private function header( string $key ): string {
		// phpcs:ignore WordPress.Security.ValidatedSanitizedInput.InputNotSanitized
		return isset( $_SERVER[ $key ] ) ? sanitize_text_field( wp_unslash( $_SERVER[ $key ] ) ) : '';
	}

	/**
	 * POST to the ALS Authenticator.
	 *
	 * @param string $path Endpoint path.
	 * @param array  $body Request body.
	 * @return array|null Decoded response, or null on failure.
	 */
	private function post_to_als( string $path, array $body ): ?array {
		$endpoint = (string) get_option( 'newshare_als_auth_endpoint', '' );
		if ( '' === $endpoint ) {
			return null;
		}

		$response = wp_remote_post(
			untrailingslashit( $endpoint ) . $path,
			array(
				'timeout'  => self::TIMEOUT,
				'blocking' => true,
				'headers'  => array( 'Content-Type' => 'application/json' ),
				'body'     => wp_json_encode( $body ),
			)
		);

		if ( is_wp_error( $response ) ) {
			return null;
		}
		$code = (int) wp_remote_retrieve_response_code( $response );
		if ( $code < 200 || $code >= 300 ) {
			return null;
		}

		$decoded = json_decode( wp_remote_retrieve_body( $response ), true );
		return is_array( $decoded ) ? $decoded : null;
	}

	/**
	 * Send a JSON response and stop.
	 *
	 * Machine callers get JSON and an accurate status code, never an HTML page
	 * describing a login they cannot perform.
	 *
	 * @param int   $status  HTTP status code.
	 * @param array $payload Response body.
	 * @param array $headers Extra headers.
	 */
	private function respond( int $status, array $payload, array $headers = array() ): void {
		status_header( $status );
		header( 'Content-Type: application/json' );
		foreach ( $headers as $name => $value ) {
			header( $name . ': ' . $value );
		}
		echo wp_json_encode( $payload );
		exit;
	}
}
