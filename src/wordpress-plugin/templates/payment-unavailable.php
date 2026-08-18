<?php
/**
 * Template: Purchase Could Not Be Attempted.
 *
 * Shown when the reader's home base could not be reached, could not be
 * resolved, or answered in a way that could not be understood. No decision was
 * made by anybody.
 *
 * This is the screen that did not exist until 0.2.6. Both outcomes rendered
 * payment-declined.php, so a network failure on our side told the reader their
 * home base had refused them and sent them there to ask about it -- attributing
 * our fault to a third party, and wasting the reader's time with a support
 * question nobody at that organization could answer.
 *
 * The remedy differs too, which is the practical reason the screens must
 * differ: a refusal is settled by changing something at the home base, and this
 * is settled by trying again.
 *
 * == Expected Variables ==
 *
 *   $decline_reason  string  What went wrong, for logs and demo narration.
 *   $home_base_name  string  The organization we could not reach, when known.
 *   $current_url     string  This article, for the try-again link.
 *
 * @package Newshare_Network
 * @since   0.2.6
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$newshare_hb = ! empty( $home_base_name )
	? $home_base_name
	: __( 'your account provider', 'newshare-network' );
$newshare_here = ! empty( $current_url ) ? $current_url : get_permalink();
?>

<div class="newshare-access-gate newshare-payment-unavailable">
	<h3><?php esc_html_e( 'We could not reach your account provider', 'newshare-network' ); ?></h3>
	<p>
		<?php
		printf(
			/* translators: %s: home base name */
			esc_html__( 'We could not ask %s to authorize this story, so nobody has decided anything and nothing has been charged. This is a fault at our end rather than yours or theirs.', 'newshare-network' ),
			esc_html( $newshare_hb )
		);
		?>
	</p>

	<p>
		<a href="<?php echo esc_url( $newshare_here ); ?>" class="newshare-login-btn">
			<?php esc_html_e( 'Try again', 'newshare-network' ); ?>
		</a>
	</p>

	<?php if ( get_option( 'newshare_show_decline_reason', false ) && ! empty( $decline_reason ) ) : ?>
		<p class="newshare-decline-reason"><em><?php echo esc_html( $decline_reason ); ?></em></p>
	<?php endif; ?>
</div>
