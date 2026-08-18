<?php
/**
 * Newshare Pricing Negotiation.
 *
 * Before this site releases paywalled content to a visiting network reader, it
 * asks that reader's home base whether it will pay the asking price. The home
 * base -- acting as the reader's Retail Agent -- accepts, counters, or declines.
 *
 * == Why this is a real exchange, not a lookup ==
 *
 * The network's pricing rules require that both the seller and the buyer of
 * usage rights be free to set their own terms and reach a binding agreement in
 * real time. A publisher may ask what it likes; a home base may refuse, or
 * offer less. All three outcomes are supported here.
 *
 * == Wholesale and retail ==
 *
 * This site only ever states and receives the WHOLESALE price -- what it is
 * owed. The reader's home base applies its own markup when billing its reader,
 * and that markup ratio is deliberately not disclosed to us. We may be told the
 * resulting retail figure so we can show the reader what they are committing
 * to, but we never learn how it was derived and we are never paid it.
 *
 * == Blocking, unlike event logging ==
 *
 * Newshare_Logger fires events asynchronously because a dropped log entry is
 * recoverable. This request is different: we must not release content before
 * knowing payment is authorized, so the call blocks. It is kept to a short
 * timeout, and a failure to reach the agent is treated as "not authorized"
 * rather than silently serving content nobody has agreed to pay for.
 *
 * @package Newshare_Network
 * @since   0.2.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Pricing {

	/**
	 * Session manager, used to read the reader's network claims.
	 *
	 * @var Newshare_Session
	 */
	private Newshare_Session $session;

	/**
	 * Seconds to wait for the reader's home base to answer.
	 *
	 * Short by design: the reader is waiting on this request. If the agent
	 * cannot answer promptly we decline rather than stall the page.
	 */
	private const QUOTE_TIMEOUT = 5;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session $session Session manager instance.
	 */
	public function __construct( Newshare_Session $session ) {
		$this->session = $session;
	}

	/**
	 * Ask the reader's home base to authorize payment for a resource.
	 *
	 * @param int $post_id The post being requested.
	 * @return array {
	 *     @type string $decision     'accept', 'decline', or 'unavailable'.
	 *     @type float  $agreed_price Wholesale price we will be settled at, on accept.
	 *     @type float  $retail_price What the reader owes their home base, on accept.
	 *     @type string $reason       Human-readable explanation.
	 * }
	 */
	public function negotiate( int $post_id ): array {
		$claims = $this->session->get_network_claims();
		if ( empty( $claims ) ) {
			return $this->unavailable( __( 'No network session.', 'newshare-network' ) );
		}

		$home_base = $this->resolve_home_base( $claims['newshare_home_base_id'] ?? '' );
		$agent_url = (string) ( $home_base['agent_url'] ?? '' );
		if ( '' === $agent_url ) {
			return $this->unavailable(
				__( 'Could not locate the reader\'s home base agent.', 'newshare-network' )
			);
		}

		// Kept so a refusal can point the reader back to the party that made
		// the decision, per the specified copy.
		// Where a person can go, not where software goes.
		//
		// This used to be the OIDC issuer, which meant a reader refused a
		// purchase was sent to an identity endpoint -- infrastructure, with
		// nothing on it they could read or act on. The registry now carries an
		// account_url for exactly this, and falls back to the realm's own
		// account console, which is at least a page built for a human.
		$home_base_url  = (string) ( $home_base['account_url'] ?? '' );
		if ( '' === $home_base_url ) {
			$issuer        = (string) ( $home_base['oidc_issuer'] ?? '' );
			$home_base_url = '' === $issuer ? '' : untrailingslashit( $issuer ) . '/account/';
		}
		$home_base_name = (string) ( $home_base['name'] ?? '' );

		$wholesale = $this->get_page_class( $post_id );

		// ---------------------------------------------------------------
		// Round one: post the price.
		//
		// A publisher that never wants to haggle sets "Posted prices are
		// final" and the exchange is over in one trip: the agent may accept
		// or decline, nothing else.
		// ---------------------------------------------------------------
		$always_final = (bool) get_option( 'newshare_posted_price_is_final', false );
		$offer        = $this->send_quote(
			$agent_url,
			$post_id,
			$claims,
			$wholesale,
			'',
			$always_final ? 'final' : 'open'
		);
		if ( null === $offer ) {
			return $this->unavailable(
				__( 'The reader\'s home base could not be reached.', 'newshare-network' ),
				$home_base_url,
				$home_base_name
			);
		}

		// ---------------------------------------------------------------
		// Round two: the agent asked to negotiate. We now decide whether to
		// meet it or hold our price -- the choice the demo script gives the
		// publisher. We meet the agent when its preferred figure clears our
		// floor; otherwise we re-post the same price as final, and the agent
		// gets one last turn to take it or leave it.
		// ---------------------------------------------------------------
		if ( 'negotiate' === ( $offer['decision'] ?? '' ) ) {
			$desired = (float) ( $offer['desiredPrice'] ?? 0 );
			$floor   = (float) get_option( 'newshare_minimum_page_class', 0 );

			if ( $desired >= $floor ) {
				$next_price = $desired;   // meet them
				$next_terms = 'open';
			} else {
				$next_price = $wholesale; // hold firm
				$next_terms = 'final';
			}

			$offer = $this->send_quote(
				$agent_url,
				$post_id,
				$claims,
				$next_price,
				(string) ( $offer['negotiationId'] ?? '' ),
				$next_terms
			);
			if ( null === $offer ) {
				return $this->unavailable(
					__( 'The reader\'s home base could not be reached.', 'newshare-network' ),
					$home_base_url
				);
			}
		}

		if ( 'accept' === ( $offer['decision'] ?? '' ) ) {
			return array(
				'decision'      => 'accept',
				'agreed_price'  => (float) ( $offer['agreedPrice'] ?? 0 ),
				'retail_price'  => (float) ( $offer['retailPrice'] ?? 0 ),
				'reason'        => (string) ( $offer['reason'] ?? '' ),
				'home_base_url' => $home_base_url,
			'home_base_name' => $home_base_name,
			);
		}

		return array(
			'decision'      => 'decline',
			'reason'        => (string) ( $offer['reason'] ?? '' ),
			'home_base_url' => $home_base_url,
			'home_base_name' => $home_base_name,
		);
	}

	/**
	 * POST a single offer to the reader's home base agent.
	 *
	 * @param string $agent_url       Base URL of the agent service.
	 * @param int    $post_id         Post being priced.
	 * @param array  $claims          The reader's network claims.
	 * @param float  $wholesale       Price we are posting.
	 * @param string $negotiation_id  Set when continuing an exchange.
	 * @param string $terms           'open' (negotiable) or 'final' (take it or leave it).
	 * @return array|null Decoded response, or null if the agent was unreachable.
	 */
	private function send_quote(
		string $agent_url,
		int $post_id,
		array $claims,
		float $wholesale,
		string $negotiation_id,
		string $terms = 'open'
	): ?array {
		$response = wp_remote_post(
			trailingslashit( $agent_url ) . 'agent/quote',
			array(
				'timeout'  => self::QUOTE_TIMEOUT,
				'blocking' => true,
				'headers'  => array( 'Content-Type' => 'application/json' ),
				'body'     => wp_json_encode(
					array(
						'networkUserId'  => $claims['newshare_network_user_id'] ?? '',
						'homeBaseId'     => $claims['newshare_home_base_id'] ?? '',
						'pubMbrId'       => get_option( 'newshare_pub_mbr_id', '' ),
						'resourceId'     => get_permalink( $post_id ),
						'wholesalePrice' => $wholesale,
						'sessionId'      => $claims['newshare_session_id'] ?? '',
						'negotiationId'  => $negotiation_id,
						'terms'          => $terms,
					)
				),
			)
		);

		if ( is_wp_error( $response ) ) {
			return null;
		}
		if ( 200 !== (int) wp_remote_retrieve_response_code( $response ) ) {
			return null;
		}

		$decoded = json_decode( wp_remote_retrieve_body( $response ), true );
		return is_array( $decoded ) ? $decoded : null;
	}

	/**
	 * Look up a home base in the ITEGA network registry.
	 *
	 * Read from the registry rather than configured per site, so a publisher
	 * does not need reconfiguring every time the network certifies another home
	 * base. Cached briefly, since the registry changes only when ITEGA
	 * certifies or suspends a member.
	 *
	 * @param string $home_base_id ITEGA identifier of the reader's home base.
	 * @return array Registry record, or an empty array if unknown.
	 */
	private function resolve_home_base( string $home_base_id ): array {
		if ( '' === $home_base_id ) {
			return array();
		}

		$cache_key = 'newshare_home_base_' . md5( $home_base_id );
		$cached    = get_transient( $cache_key );
		if ( false !== $cached && is_array( $cached ) ) {
			return $cached;
		}

		$discovery = get_option( 'newshare_discovery_endpoint', '' );
		if ( '' === $discovery ) {
			return array();
		}

		$response = wp_remote_get(
			trailingslashit( $discovery ) . 'discovery/home-bases/' . rawurlencode( $home_base_id ),
			array( 'timeout' => self::QUOTE_TIMEOUT )
		);
		if ( is_wp_error( $response ) || 200 !== (int) wp_remote_retrieve_response_code( $response ) ) {
			return array();
		}

		$decoded = json_decode( wp_remote_retrieve_body( $response ), true );
		if ( ! is_array( $decoded ) ) {
			return array();
		}

		set_transient( $cache_key, $decoded, 5 * MINUTE_IN_SECONDS );
		return $decoded;
	}

	/**
	 * The publisher's asking price for a post, falling back to the site default.
	 *
	 * @param int $post_id Post to price.
	 * @return float Wholesale price.
	 */
	private function get_page_class( int $post_id ): float {
		$page_class = get_post_meta( $post_id, 'newshare_page_class', true );
		if ( '' === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}
		return (float) $page_class;
	}

	/**
	 * Build an 'unavailable' result.
	 *
	 * Distinct from 'decline': the home base did not refuse, we simply could
	 * not complete the exchange. Both withhold content, but only a decline
	 * reflects a decision the home base actually made.
	 *
	 * @param string $reason         Explanation for logs.
	 * @param string $home_base_url  Reader's home base, when known.
	 * @param string $home_base_name Its name, for copy that addresses a person.
	 * @return array Result array.
	 */
	private function unavailable( string $reason, string $home_base_url = '', string $home_base_name = '' ): array {
		return array(
			'decision'       => 'unavailable',
			'reason'         => $reason,
			'home_base_url'  => $home_base_url,
			'home_base_name' => $home_base_name,
		);
	}
}
