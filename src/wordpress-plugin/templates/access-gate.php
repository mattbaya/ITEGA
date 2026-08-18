<?php
/**
 * Template: Access Gate.
 *
 * Displayed when content is behind a subscription tier wall. This template
 * replaces the full article content with a truncated preview and one of two
 * messages:
 *
 *   1. For anonymous users (not logged in via the network):
 *      A "Network Login" button that initiates the OIDC flow.
 *
 *   2. For authenticated network users with insufficient access tier:
 *      A message explaining which subscription tier is required and
 *      directing them to upgrade through their home base.
 *
 * == Expected Variables ==
 *
 * These variables are set by Newshare_Access::filter_content() before this
 * template is included via ob_start()/ob_get_clean():
 *
 *   $tier_name       string  Human-readable name of the required subscription tier
 *                            (e.g., "Paid Subscriber", "Digital Subscriber + Paid Subscriber").
 *   $is_network_user bool    Whether the current user has an active network session.
 *   $current_url     string  The canonical URL of the current article (for return-after-login).
 *
 * @package Newshare_Network
 * @since   0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>

<div class="newshare-access-gate">
	<?php if ( $is_network_user ) : ?>
		<?php
		// -----------------------------------------------------------------
		// Authenticated network user, but insufficient subscription tier.
		// They need to upgrade their subscription through their home base.
		// -----------------------------------------------------------------
		?>
		<h3><?php esc_html_e( 'Subscription Required', 'newshare-network' ); ?></h3>
		<p>
			<?php
			// -----------------------------------------------------------------
			// FIX (MAJOR): Use wp_kses() instead of esc_html__() for strings
			// containing HTML.
			//
			// Previously, this used:
			//   printf( esc_html__( '...%s...'), '<strong>...</strong>' );
			//
			// While that specific pattern happened to work (because %s is
			// substituted AFTER esc_html__ escapes the format string, and %s
			// itself is not an HTML entity), it is an antipattern because:
			//   a) If a translator includes HTML in the translated string, it
			//      will be escaped and display as raw text.
			//   b) WordPress coding standards recommend separating translatable
			//      text from HTML markup.
			//
			// The fix: use a plain translated string for the text, and wrap
			// the variable in HTML separately. wp_kses() ensures only allowed
			// HTML tags are preserved in the output.
			// -----------------------------------------------------------------
			$tier_html = '<strong>' . esc_html( $tier_name ) . '</strong>';
			$message = sprintf(
				/* translators: %s: the required subscription tier name wrapped in <strong> tags */
				__( 'This content requires %s access. Please upgrade your subscription through your home base to continue reading.', 'newshare-network' ),
				$tier_html
			);
			echo wp_kses( $message, array( 'strong' => array() ) );
			?>
		</p>
	<?php else : ?>
		<?php
		// -----------------------------------------------------------------
		// Anonymous user (not logged in via the network).
		// Show a login prompt with the "Network Login" button.
		// -----------------------------------------------------------------
		?>
		<h3><?php esc_html_e( 'Continue Reading', 'newshare-network' ); ?></h3>
		<p>
			<?php esc_html_e( 'This article is included if you hold an account at any newspaper in the network — not just this one.', 'newshare-network' ); ?>
		</p>
		<?php
		// Say what it costs.
		//
		// A wall that asks you to sign in without naming a number invites the
		// reader to imagine a subscription, which is the anxiety this whole
		// arrangement exists to remove. But the exact figure is the
		// publisher's asking price, not the reader's bill: their home base
		// adds its own margin, and this site is deliberately never told what
		// that margin is. So the number is given as what the newspaper is
		// paid, with the difference acknowledged rather than papered over.
		$newshare_price = isset( $page_class ) ? (float) $page_class : 0.0;
		if ( $newshare_price > 0 ) :
			$newshare_shown = $newshare_price < 1
				? sprintf( '%d&cent;', (int) round( $newshare_price * 100 ) )
				: sprintf( '$%s', number_format( $newshare_price, 2 ) );
			?>
			<p class="newshare-price">
				<?php
				printf(
					/* translators: %s: the publisher's price for this article, e.g. 5¢ */
					esc_html__( 'This story costs %s. Not a subscription, and no card details — your account is with your own newspaper, and it settles up on your behalf.', 'newshare-network' ),
					wp_kses_post( $newshare_shown )
				);
				?>
			</p>
		<?php endif; ?>
		<p class="newshare-already">
			<?php esc_html_e( 'Already signed in somewhere in the network? You will not be asked for a password. This publisher cannot tell, by design — it never sees who you are until you choose to continue.', 'newshare-network' ); ?>
		</p>

		<?php
		// -----------------------------------------------------------------
		// Build the login URL with the return URL.
		//
		// FIX (MAJOR): Pass the current article URL as newshare_return_to
		// so the user is redirected back to this article after login,
		// instead of ending up at wp-login.php or the home page.
		// -----------------------------------------------------------------
		$newshare_login_url = add_query_arg(
			array(
				'newshare_login'     => '1',
				'newshare_nonce'     => wp_create_nonce( 'newshare_login_initiate' ),
				'newshare_return_to' => isset( $current_url ) ? $current_url : get_permalink(),
			),
			home_url( '/' )
		);
		?>

		<a href="<?php echo esc_url( $newshare_login_url ); ?>" class="newshare-login-btn">
			<span class="newshare-icon">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
					<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
				</svg>
			</span>
			<?php esc_html_e( 'Continue with your news network account', 'newshare-network' ); ?>
		</a>
	<?php endif; ?>
</div>
