<?php
/**
 * Logout: let the reader choose how far the sign-out reaches.
 *
 * Signing out of a federated network is not one act. A reader at home wants
 * the site to forget them; a reader on a library machine wants the network to
 * forget them, or the next person at that desk can buy articles billed to
 * their account. WordPress only knows how to do the first, so the plugin asks
 * which was meant and carries out the answer.
 *
 *   Sign out here        Ends the session with this publisher. The reader
 *                        stays signed in to the network, so the next member
 *                        site still recognises them without a password --
 *                        which is the whole point of the network, and not
 *                        something to throw away by accident.
 *
 *   Sign out everywhere  Ends the network session and the session at the
 *                        reader's home base with it. The next visit anywhere
 *                        starts from scratch.
 *
 * "Here" has to reach the ALS too. The Authenticator caches the token it
 * issued for each publisher, so a reader who logs out of WordPress alone and
 * clicks a gated article is handed that cached token and silently signed back
 * in. The local logout only becomes real once that token is dropped.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Presents the sign-out choice and carries it out.
 */
class Newshare_Logout {

	/**
	 * Session reader, used to tell a network reader from an ordinary WP user.
	 *
	 * @var Newshare_Session
	 */
	private $session;

	/**
	 * Demo-mode gate. On a live publisher running a limited trial, readers
	 * outside the trial must see the site exactly as it was.
	 *
	 * @var Newshare_Demo_Mode
	 */
	private $demo;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session   $session Session reader.
	 * @param Newshare_Demo_Mode $demo    Demo-mode gate.
	 */
	public function __construct( Newshare_Session $session, Newshare_Demo_Mode $demo ) {
		$this->session = $session;
		$this->demo    = $demo;
	}

	/**
	 * Whether this request should be offered the network sign-out choice.
	 *
	 * Editors and administrators are excluded deliberately: they sign in with
	 * a WordPress password, not through the network, so a network sign-out
	 * would mean nothing to them and a confirmation page would only be in the
	 * way.
	 *
	 * @return bool
	 */
	private function applies(): bool {
		return $this->demo->is_participant() && $this->session->is_network_user();
	}

	/**
	 * Point the reader's logout link at the choice, not straight out.
	 *
	 * @param string $logout_url The URL WordPress built.
	 * @param string $redirect   Where WordPress intended to land afterwards.
	 * @return string
	 */
	public function filter_logout_url( string $logout_url, string $redirect ): string {
		if ( ! $this->applies() ) {
			return $logout_url;
		}

		return add_query_arg(
			array(
				'newshare_logout' => 'choose',
				'newshare_nonce'  => wp_create_nonce( 'newshare_logout' ),
				'newshare_return' => rawurlencode( $redirect ? $redirect : home_url( '/' ) ),
			),
			home_url( '/' )
		);
	}

	/**
	 * Handle both the choice page and the choice itself.
	 *
	 * Hooked early on `init` so it runs before the theme renders anything.
	 */
	public function handle_request(): void {
		if ( ! isset( $_GET['newshare_logout'] ) ) {
			return;
		}

		// Signing someone out is a state change, so it is protected against
		// being triggered from another site by a nonce, exactly as WordPress
		// protects its own logout link.
		if (
			! isset( $_GET['newshare_nonce'] )
			|| ! wp_verify_nonce(
				sanitize_text_field( wp_unslash( $_GET['newshare_nonce'] ) ),
				'newshare_logout'
			)
		) {
			wp_die(
				esc_html__( 'That sign-out link has expired. Please try again.', 'newshare-network' ),
				esc_html__( 'Link expired', 'newshare-network' ),
				array( 'response' => 403 )
			);
		}

		$action = sanitize_text_field( wp_unslash( $_GET['newshare_logout'] ) );
		$return = isset( $_GET['newshare_return'] )
			? esc_url_raw( wp_unslash( rawurldecode( $_GET['newshare_return'] ) ) )
			: home_url( '/' );

		// Never send the reader off this site on the way out; an attacker who
		// could set this would have a logout link that lands anywhere.
		if ( ! $this->is_local_url( $return ) ) {
			$return = home_url( '/' );
		}

		if ( 'choose' === $action ) {
			$this->render_choice( $return );
			exit;
		}

		if ( 'here' === $action || 'everywhere' === $action ) {
			$this->perform( $action, $return );
			exit;
		}
	}

	/**
	 * Whether a URL belongs to this site.
	 *
	 * @param string $url URL to test.
	 * @return bool
	 */
	private function is_local_url( string $url ): bool {
		if ( '' === $url ) {
			return false;
		}
		$host = wp_parse_url( $url, PHP_URL_HOST );
		if ( null === $host ) {
			return true; // A path-only URL is by definition on this site.
		}
		return strtolower( $host ) === strtolower( (string) wp_parse_url( home_url(), PHP_URL_HOST ) );
	}

	/**
	 * End the WordPress session, then hand off to the ALS.
	 *
	 * The local session goes first. If the ALS were unreachable the reader
	 * would otherwise be left signed in to the site they just asked to leave,
	 * which is the failure that matters most on a shared machine.
	 *
	 * @param string $scope  'here' or 'everywhere'.
	 * @param string $return Where to land afterwards.
	 */
	private function perform( string $scope, string $return ): void {
		wp_logout();

		$als        = get_option( 'newshare_als_auth_endpoint' );
		$pub_mbr_id = get_option( 'newshare_pub_mbr_id' );
		$client_id  = get_option( 'newshare_als_client_id' );

		if ( empty( $als ) ) {
			// Nothing to hand off to; the local sign-out still happened.
			wp_safe_redirect( $return );
			return;
		}

		$url = add_query_arg(
			array(
				'scope'        => $scope,
				'pub_mbr_id'   => rawurlencode( (string) $pub_mbr_id ),
				'client_id'    => rawurlencode( (string) $client_id ),
				'redirect_uri' => rawurlencode( $return ),
			),
			trailingslashit( $als ) . 'auth/logout'
		);

		// Deliberately not wp_safe_redirect(): this leaves the site for the
		// ALS, which is the one external host the plugin is configured to
		// trust, and wp_safe_redirect() would silently rewrite it to home.
		wp_redirect( $url );
	}

	/**
	 * Ask which sign-out was meant.
	 *
	 * @param string $return Where to land afterwards.
	 */
	private function render_choice( string $return ): void {
		$here = add_query_arg(
			array(
				'newshare_logout' => 'here',
				'newshare_nonce'  => wp_create_nonce( 'newshare_logout' ),
				'newshare_return' => rawurlencode( $return ),
			),
			home_url( '/' )
		);

		$everywhere = add_query_arg(
			array(
				'newshare_logout' => 'everywhere',
				'newshare_nonce'  => wp_create_nonce( 'newshare_logout' ),
				'newshare_return' => rawurlencode( $return ),
			),
			home_url( '/' )
		);

		$site = get_bloginfo( 'name' );

		require __DIR__ . '/../templates/logout-choice.php';
	}
}
