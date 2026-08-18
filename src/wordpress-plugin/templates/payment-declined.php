<?php
/**
 * Template: Purchase Declined.
 *
 * Shown when the reader's home base was reached, understood the offer, and
 * refused it. A decision was made, by a named organization, and the reader can
 * go and ask them about it.
 *
 * Deliberately distinct from payment-unavailable.php, which covers the case
 * where no decision was made because the home base could not be reached. Both
 * withhold the article, and until 0.2.6 both showed this screen -- so an
 * infrastructure failure told the reader their home base had refused, and sent
 * them to argue with a party that knew nothing about it.
 *
 * == Expected Variables ==
 *
 *   $decline_reason   string  The agent's stated reason. Shown only where the
 *                             site operator enables it; the terms between a
 *                             reader and their home base are not this
 *                             publisher's business to publish.
 *   $home_base_url    string  Where a person can act -- an account console or
 *                             the home base's own site, never an OIDC issuer.
 *   $home_base_name   string  The organization that made the decision.
 *   $newshare_asking  string  The publisher's asking price, already formatted.
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
?>

<div class="newshare-access-gate newshare-payment-declined">
	<h3><?php esc_html_e( 'Your account did not authorize this purchase', 'newshare-network' ); ?></h3>
	<p>
		<?php
		if ( ! empty( $newshare_asking ) ) {
			printf(
				/* translators: 1: home base name, 2: the publisher's asking price */
				esc_html__( '%1$s did not approve buying this story at the %2$s this publication asks for it. Nothing has been charged.', 'newshare-network' ),
				esc_html( $newshare_hb ),
				esc_html( $newshare_asking )
			);
		} else {
			printf(
				/* translators: %s: home base name */
				esc_html__( '%s did not approve buying this story. Nothing has been charged.', 'newshare-network' ),
				esc_html( $newshare_hb )
			);
		}
		?>
	</p>
	<p>
		<?php
		printf(
			/* translators: %s: home base name */
			esc_html__( 'The decision is theirs rather than this publication\'s, and so are the settings behind it. %s can tell you what your options are.', 'newshare-network' ),
			esc_html( $newshare_hb )
		);
		?>
	</p>

	<?php if ( ! empty( $home_base_url ) ) : ?>
		<p>
			<a href="<?php echo esc_url( $home_base_url ); ?>" class="newshare-login-btn">
				<?php
				printf(
					/* translators: %s: home base name */
					esc_html__( 'Review my account at %s', 'newshare-network' ),
					esc_html( $newshare_hb )
				);
				?>
			</a>
		</p>
	<?php endif; ?>

	<?php if ( get_option( 'newshare_show_decline_reason', false ) && ! empty( $decline_reason ) ) : ?>
		<p class="newshare-decline-reason"><em><?php echo esc_html( $decline_reason ); ?></em></p>
	<?php endif; ?>
</div>
