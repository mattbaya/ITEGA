<?php
/**
 * Newshare Event Logger.
 *
 * This class logs content access events to the ALS (Auth/Logging/Settlement)
 * logging endpoint. The ALS aggregates these events across all publishers in
 * the Newshare Network for settlement (revenue sharing) and analytics.
 *
 * == Fire-and-Forget Logging Model ==
 *
 * Event logging uses a non-blocking HTTP POST (blocking=false, timeout=2s).
 * This "fire-and-forget" approach is critical because:
 *
 *   1. Page rendering must NOT be delayed by logging. A slow or unavailable
 *      ALS logging endpoint should never degrade the reader's experience.
 *   2. The ALS logging service is designed to tolerate dropped events.
 *      Settlement uses batch reconciliation, not real-time event counting.
 *   3. WordPress's wp_remote_post() with blocking=false dispatches the HTTP
 *      request and immediately returns without waiting for a response.
 *
 * == Privacy Model ==
 *
 * Only opaque identifiers are sent to the ALS:
 *   - networkUserId: PPID (different per publisher, cannot be correlated)
 *   - homeBaseId: identifies which home base authenticated the user
 *   - pubMbrId: identifies this publisher
 *   - sessionId: opaque session reference
 *
 * No PII (name, email, IP address, user-agent) is included in the event.
 * The ALS cannot identify real people from these events.
 *
 * == Event Payload (Extended Common Log Format) ==
 *
 * The event payload includes pricing fields needed for settlement:
 *   - pageClass: wholesale price set by the publisher (e.g., $0.05)
 *   - serviceClass: the user's NetworkGroupId bitmask (subscription tier)
 *   - markupRatio: the home base's retail markup multiplier
 *
 * @package Newshare_Network
 * @since   0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Logger {

	/**
	 * Session manager instance.
	 *
	 * Used to check if the current user is a network user and to retrieve
	 * their network claims (opaque identifiers) for the event payload.
	 *
	 * @var Newshare_Session
	 */
	private Newshare_Session $session;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session $session Session manager (injected by the main plugin class).
	 */
	public function __construct( Newshare_Session $session ) {
		$this->session = $session;
	}

	// =========================================================================
	// Event Logging
	// =========================================================================

	/**
	 * Log a content access event to the ALS.
	 *
	 * Called from template_redirect (via Newshare_Network::handle_template_redirect)
	 * when a network user successfully accesses a post. This records the event
	 * for later settlement (revenue sharing between publishers and home bases).
	 *
	 * The request is fire-and-forget (non-blocking) -- we do NOT wait for the
	 * ALS to acknowledge the event. This ensures logging never slows down page
	 * rendering, even if the ALS is slow or temporarily unreachable.
	 *
	 * @param int $post_id The post ID being accessed.
	 */
	public function log_content_access( int $post_id ): void {
		// Only log events for users with an active network session.
		// Anonymous users and local-only WP users are not logged.
		if ( ! $this->session->is_network_user() ) {
			return;
		}

		// Retrieve ALS logging configuration.
		$logging_endpoint = get_option( 'newshare_als_logging_endpoint' );
		$api_key          = get_option( 'newshare_als_api_key' );

		// Silently skip if logging is not configured (e.g., during initial setup).
		if ( empty( $logging_endpoint ) || empty( $api_key ) ) {
			return;
		}

		// Get the current user's network claims from user meta.
		$claims = $this->session->get_network_claims();

		// Determine pageClass: per-post override takes precedence over site default.
		// pageClass is the wholesale price the publisher charges for this content.
		$page_class = get_post_meta( $post_id, 'newshare_page_class', true );
		if ( '' === $page_class || false === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}

		// Build the event payload following the Extended Common Log Format.
		// All identifiers are opaque -- no PII is included.
		$event = array(
			'networkUserId' => $claims['newshare_network_user_id'] ?? '',   // PPID (unique per publisher).
			'homeBaseId'    => $claims['newshare_home_base_id'] ?? '',      // Which home base authenticated the user.
			'pubMbrId'      => get_option( 'newshare_pub_mbr_id', '' ),    // This publisher's network member ID.
			'resourceId'    => get_permalink( $post_id ),                   // The canonical URL of the accessed content.
			'pageClass'     => (float) $page_class,                        // Wholesale price (set by publisher).
			'serviceClass'  => (int) ( $claims['newshare_network_group_id'] ?? 0 ), // User's subscription tier bitmask.
			'markupRatio'   => (float) ( $claims['newshare_markup_ratio'] ?? 1.0 ), // Home base's retail markup multiplier.
			'eventType'     => 'content_access',                           // Event type enum (content_access | ad_view | subscription_credit | reward).
			'sessionId'     => $claims['newshare_session_id'] ?? '',       // Opaque session reference.
			'timestamp'     => gmdate( 'c' ),                              // ISO 8601 timestamp in UTC.
			// Identifies this record as the content site's own. The reader's
			// home base files a separate record for the same purchase so the
			// two can be audited against each other; settlement aggregates
			// this side, so the distinction must be explicit or every sale
			// would be counted twice.
			'reporter'      => 'cms',
		);

		/**
		 * Filters the event payload before sending to the ALS.
		 *
		 * Allows themes or other plugins to modify or augment the event data.
		 * For example, adding custom fields for A/B testing or content categories.
		 *
		 * @param array $event   The event data to be sent.
		 * @param int   $post_id The post ID being accessed.
		 */
		$event = apply_filters( 'newshare_log_event', $event, $post_id );

		$url = trailingslashit( $logging_endpoint ) . 'event';

		// -----------------------------------------------------------------
		// Fire-and-forget: non-blocking POST with a short timeout.
		//
		// blocking=false means WordPress dispatches the HTTP request and
		// returns immediately without waiting for a response. The 2-second
		// timeout is a safety net for the underlying transport (cURL) --
		// in practice, the function returns instantly due to blocking=false.
		//
		// If the ALS is down, the event is silently dropped. This is
		// acceptable because settlement uses batch reconciliation and can
		// tolerate missing individual events.
		// -----------------------------------------------------------------
		wp_remote_post(
			$url,
			array(
				'body'     => wp_json_encode( $event ),
				'headers'  => array(
					'Content-Type' => 'application/json',
					'X-API-Key'    => $api_key,
				),
				'timeout'  => 2,
				'blocking' => false,
			)
		);
	}
}
