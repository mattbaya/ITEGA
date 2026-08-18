<?php
/**
 * The network status badge.
 *
 * == Why this exists ==
 *
 * A reader could not tell whether they were signed in to the network. On one
 * site WordPress happened to render its admin bar -- "Howdy, ITEGA Guest
 * 948AFC" -- and on another it did not, so the same person browsing two
 * network newspapers saw their status on one and nothing on the other.
 * Reading several articles without being stopped looked like a broken
 * paywall, when in fact they were signed in and being billed correctly.
 *
 * Relying on the admin bar was never right. It is WordPress chrome, not
 * network chrome: themes suppress it, it greets people with "Howdy", and it
 * says nothing about the network when a visitor is signed out. A reader's
 * relationship with the network is the plugin's business to display, so the
 * plugin displays it.
 *
 * == What it shows ==
 *
 * Signed in:  the pairwise identifier this publisher knows them by -- which
 *             is also a quiet demonstration that the publisher knows nothing
 *             else -- and a way out.
 * Signed out: that they are signed out, and a way in.
 *
 * Both states matter. The report that prompted this was that a reader flying
 * blind cannot tell a working paywall from a broken one, and silence looks
 * identical either way.
 *
 * == What it must never do ==
 *
 * Appear for an ordinary reader of a publisher running in demo mode. Greylock
 * Glass agreed to host the plugin on the condition that its readers never see
 * it, and a badge in the corner of every page would break that promise more
 * visibly than anything else here. should_suppress() is checked before any
 * markup is emitted.
 *
 * @package Newshare_Network
 * @since   0.2.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Status {

	private Newshare_Session $session;
	private Newshare_Demo_Mode $demo;

	public function __construct( Newshare_Session $session, Newshare_Demo_Mode $demo ) {
		$this->session = $session;
		$this->demo    = $demo;
	}

	/**
	 * Whether to show the badge at all on this request.
	 */
	private function should_show(): bool {
		// Never in an admin screen, a feed, an AJAX or REST call. Those have
		// their own furniture and are not reader-facing.
		if ( is_admin() || is_feed() || wp_doing_ajax()
			|| ( defined( 'REST_REQUEST' ) && REST_REQUEST ) ) {
			return false;
		}

		// Demo mode wins over everything. A publisher hosting this quietly
		// must stay quiet.
		if ( $this->demo->should_suppress() ) {
			return false;
		}

		// A publisher's own staff already have the admin bar, and do not need
		// telling about a network session they do not have.
		if ( is_user_logged_in() && ! $this->session->is_network_user() ) {
			return false;
		}

		/**
		 * Let a publisher turn the badge off without turning the plugin off.
		 *
		 * @param bool $show Whether to render the network status badge.
		 */
		return (bool) apply_filters( 'newshare_show_status_badge', true );
	}

	/**
	 * Print the badge.
	 *
	 * Hooked to wp_footer and positioned with CSS, so it needs nothing from
	 * the theme and cannot disturb a layout it knows nothing about.
	 */
	public function render(): void {
		if ( ! $this->should_show() ) {
			return;
		}

		$signed_in = $this->session->is_network_user() && $this->session->is_session_valid();

		if ( $signed_in ) {
			$claims = $this->session->get_network_claims();
			$id     = (string) ( $claims['newshare_network_user_id'] ?? '' );
			$short  = strtoupper( substr( preg_replace( '/[^a-zA-Z0-9]/', '', $id ), 0, 6 ) );

			/* translators: %s: short opaque reader code */
			$label       = sprintf( __( 'ITEGA Guest %s', 'newshare-network' ), $short );
			$action_url  = wp_logout_url( home_url() );
			$action_text = __( 'Sign out', 'newshare-network' );
			$dot         = '#2e7d4f';
			$title       = __( 'You are signed in to the Newshare network. This publisher knows you only by this code.', 'newshare-network' );
		} else {
			$label = __( 'Not signed in', 'newshare-network' );
			// Aim the link at the article being read, so signing in returns
			// them to it rather than to the front page.
			// Nonced, because maybe_initiate_login() checks one -- a link
			// without it fails on click and looks like a broken sign-in.
			$action_url = wp_nonce_url(
				add_query_arg(
					'newshare_login',
					'1',
					( is_singular() && get_the_ID() ) ? get_permalink() : home_url()
				),
				'newshare_login_initiate',
				'newshare_nonce'
			);
			$action_text = __( 'Sign in', 'newshare-network' );
			$dot         = '#8a8f93';
			$title       = __( 'You are reading anonymously. Articles you open count towards this publisher\'s free allowance.', 'newshare-network' );
		}
		?>
		<div class="newshare-status" title="<?php echo esc_attr( $title ); ?>">
			<span class="newshare-status__dot" style="background:<?php echo esc_attr( $dot ); ?>"></span>
			<span class="newshare-status__label"><?php echo esc_html( $label ); ?></span>
			<a class="newshare-status__action" href="<?php echo esc_url( $action_url ); ?>"><?php echo esc_html( $action_text ); ?></a>
		</div>
		<style>
		.newshare-status{position:fixed;top:0;right:0;z-index:99999;display:flex;
		  align-items:center;gap:.5em;padding:.4em .8em;
		  font:13px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
		  background:rgba(255,255,255,.96);color:#23282b;
		  border:1px solid rgba(0,0,0,.12);border-top:0;border-right:0;
		  border-radius:0 0 0 4px;box-shadow:0 1px 6px rgba(0,0,0,.08)}
		.newshare-status__dot{width:7px;height:7px;border-radius:50%;flex:0 0 auto}
		.newshare-status__label{white-space:nowrap}
		.newshare-status__action{color:#2a5c6b;text-decoration:underline;white-space:nowrap}
		.newshare-status__action:hover{text-decoration:none}
		@media (prefers-color-scheme:dark){
		  .newshare-status{background:rgba(24,30,34,.96);color:#e6eaec;
		    border-color:rgba(255,255,255,.14)}
		  .newshare-status__action{color:#7fc0d0}
		}
		/* Sit below the admin bar where there is one, rather than under it. */
		body.admin-bar .newshare-status{top:32px}
		@media screen and (max-width:782px){body.admin-bar .newshare-status{top:46px}}
		</style>
		<?php
	}
}
