<?php
/**
 * Newshare Event Logger.
 *
 * Logs content access events to the ALS logging endpoint.
 * Only opaque identifiers are sent — no PII leaves the publisher.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Logger {

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
	 * Log a content access event to the ALS.
	 *
	 * Called from template_redirect when a network user successfully
	 * accesses a post. The request is fire-and-forget (non-blocking).
	 *
	 * @param int $post_id The post ID being accessed.
	 */
	public function log_content_access( int $post_id ): void {
		// Only log for network users with valid sessions.
		if ( ! $this->session->is_network_user() ) {
			return;
		}

		$logging_endpoint = get_option( 'newshare_als_logging_endpoint' );
		$api_key          = get_option( 'newshare_als_api_key' );

		if ( empty( $logging_endpoint ) || empty( $api_key ) ) {
			return;
		}

		$claims = $this->session->get_network_claims();

		// Determine pageClass: per-post override, then site default.
		$page_class = get_post_meta( $post_id, 'newshare_page_class', true );
		if ( '' === $page_class || false === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}

		$event = array(
			'networkUserId' => $claims['newshare_network_user_id'] ?? '',
			'homeBaseId'    => $claims['newshare_home_base_id'] ?? '',
			'pubMbrId'      => get_option( 'newshare_pub_mbr_id', '' ),
			'resourceId'    => get_permalink( $post_id ),
			'pageClass'     => (float) $page_class,
			'serviceClass'  => (int) ( $claims['newshare_network_group_id'] ?? 0 ),
			'markupRatio'   => (float) ( $claims['newshare_markup_ratio'] ?? 1.0 ),
			'eventType'     => 'content_access',
			'sessionId'     => $claims['newshare_session_id'] ?? '',
			'timestamp'     => gmdate( 'c' ),
		);

		/**
		 * Filters the event payload before sending to the ALS.
		 *
		 * @param array $event   The event data.
		 * @param int   $post_id The post ID.
		 */
		$event = apply_filters( 'newshare_log_event', $event, $post_id );

		$url = trailingslashit( $logging_endpoint ) . 'event';

		// Fire-and-forget: non-blocking POST with a short timeout.
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
