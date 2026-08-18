<?php
/**
 * Template: the sign-out choice.
 *
 * Two options, not a checkbox: the difference between them is the difference
 * between a laptop and a library machine, and the reader is the only one who
 * knows which they are at. The consequence of each is written out, because
 * "everywhere" costs them the recognition at other publishers that they came
 * to the network for, and "here" leaves a session alive on the machine.
 *
 * Expects: $here, $everywhere, $return, $site.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

?><!doctype html>
<html <?php language_attributes(); ?>>
<head>
<meta charset="<?php bloginfo( 'charset' ); ?>">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title><?php esc_html_e( 'Signing out', 'newshare-network' ); ?></title>
<style>
	:root {
		--ink: #15222b; --ink-soft: #55676f; --rule: #d3dcd8;
		--paper: #f3f5f3; --card: #ffffff; --accent: #2a5c6b;
	}
	@media ( prefers-color-scheme: dark ) {
		:root {
			--ink: #e7ece9; --ink-soft: #a3b3ba; --rule: #33454d;
			--paper: #141d23; --card: #1a262d; --accent: #7fc0d0;
		}
	}
	* { box-sizing: border-box; }
	body {
		margin: 0; background: var(--paper); color: var(--ink);
		font: 17px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
		display: flex; align-items: center; justify-content: center;
		min-height: 100vh; padding: 2rem 1.25rem;
	}
	.box { max-width: 34rem; width: 100%; }
	h1 {
		font: 600 1.6rem/1.25 Georgia, "Times New Roman", serif;
		margin: 0 0 .4em; text-wrap: balance;
	}
	.lede { color: var(--ink-soft); margin: 0 0 1.75rem; }
	.choice {
		display: block; background: var(--card); border: 1px solid var(--rule);
		border-left: 3px solid var(--accent); padding: 1.1rem 1.25rem;
		margin-bottom: .85rem; text-decoration: none; color: inherit;
	}
	.choice:hover, .choice:focus-visible { border-left-width: 6px; padding-left: 1.05rem; }
	.choice:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.choice strong { display: block; font-size: 1.05rem; margin-bottom: .15rem; }
	.choice span { color: var(--ink-soft); font-size: .95rem; }
	.back { display: inline-block; margin-top: 1rem; color: var(--ink-soft); font-size: .92rem; }
</style>
</head>
<body>
<div class="box">
	<h1><?php esc_html_e( 'How far should we sign you out?', 'newshare-network' ); ?></h1>
	<p class="lede">
		<?php esc_html_e( 'Your account is with your home base, not with this newspaper, so there are two different things you might mean.', 'newshare-network' ); ?>
	</p>

	<a class="choice" href="<?php echo esc_url( $here ); ?>">
		<strong>
			<?php
			/* translators: %s: the name of this publication. */
			printf( esc_html__( 'Sign out of %s', 'newshare-network' ), esc_html( $site ) );
			?>
		</strong>
		<span><?php esc_html_e( 'Other newspapers in the network will still recognize you, and you will not need a password to read them.', 'newshare-network' ); ?></span>
	</a>

	<a class="choice" href="<?php echo esc_url( $everywhere ); ?>">
		<strong><?php esc_html_e( 'Sign out of the whole network', 'newshare-network' ); ?></strong>
		<span><?php esc_html_e( 'Ends your session at your home base too. Choose this on a shared or public computer — otherwise the next person could read, and be charged, as you.', 'newshare-network' ); ?></span>
	</a>

	<a class="back" href="<?php echo esc_url( $return ); ?>">
		<?php esc_html_e( '← Stay signed in and go back', 'newshare-network' ); ?>
	</a>
</div>
</body>
</html>
