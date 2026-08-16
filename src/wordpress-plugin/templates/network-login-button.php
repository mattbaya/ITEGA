<?php
/**
 * Template: Network Login Button.
 *
 * Renders the "Log in with your news network account" button.
 * Used on the WP login form and inside content access gates.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$newshare_login_url = add_query_arg(
	array(
		'newshare_login' => '1',
		'newshare_nonce' => wp_create_nonce( 'newshare_login_initiate' ),
	),
	home_url( '/' )
);
?>

<div class="newshare-login-wrapper">
	<div class="newshare-login-separator">
		<?php esc_html_e( 'or', 'newshare-network' ); ?>
	</div>
	<a href="<?php echo esc_url( $newshare_login_url ); ?>" class="newshare-login-btn">
		<span class="newshare-icon">
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
				<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
			</svg>
		</span>
		<?php esc_html_e( 'Continue with your news network account', 'newshare-network' ); ?>
	</a>
</div>
