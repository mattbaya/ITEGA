<?php
/**
 * Template: Payment Declined.
 *
 * Shown when a reader has a valid network session, but their home base did not
 * authorise payment for this article -- either refusing the price outright, or
 * proving unreachable.
 *
 * This is deliberately distinct from the tier-upgrade message in
 * access-gate.php. There the reader's subscription simply does not cover the
 * content and the remedy is to upgrade. Here the decision was made by the
 * reader's home base, which is the only party that can explain or change it,
 * so the message sends them there rather than trying to sell them something.
 *
 * The wording follows the network's specified copy for a declined purchase.
 *
 * == Expected Variables ==
 *
 *   $decline_reason  string  The agent's stated reason, for logs and demo
 *                            narration. Not shown to the reader by default --
 *                            pricing policy is between them and their home base.
 *   $home_base_url   string  The reader's home base, for the follow-up link.
 *                            May be empty if the registry lookup failed.
 *
 * @package Newshare_Network
 * @since   0.2.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>

<div class="newshare-access-gate newshare-payment-declined">
	<h3><?php esc_html_e( 'Content Not Available', 'newshare-network' ); ?></h3>
	<p>
		<?php
		esc_html_e(
			'Your requested content is not available at this time. Please contact your ITEGA Home Base for options.',
			'newshare-network'
		);
		?>
	</p>

	<?php
	// ---------------------------------------------------------------------
	// Link the reader back to their own home base -- the party that declined,
	// and the only one able to do anything about it. The URL comes from the
	// ITEGA registry, so no particular home base is hard-coded here.
	// ---------------------------------------------------------------------
	if ( ! empty( $home_base_url ) ) :
		?>
		<p>
			<a href="<?php echo esc_url( $home_base_url ); ?>" class="newshare-login-btn">
				<?php esc_html_e( 'Go to your home base', 'newshare-network' ); ?>
			</a>
		</p>
	<?php endif; ?>

	<?php
	// Surface the agent's reason only where the site operator has explicitly
	// enabled it. It is useful when narrating the demonstration, but in normal
	// operation the terms between a reader and their home base are not this
	// publisher's business to display.
	if ( get_option( 'newshare_show_decline_reason', false ) && ! empty( $decline_reason ) ) :
		?>
		<p class="newshare-decline-reason"><em><?php echo esc_html( $decline_reason ); ?></em></p>
	<?php endif; ?>
</div>
