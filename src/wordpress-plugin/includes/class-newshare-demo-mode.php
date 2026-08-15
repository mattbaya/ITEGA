<?php
/**
 * Newshare Demo Mode.
 *
 * Lets the plugin be installed on a real, operating news site without any of
 * its behaviour reaching that site's ordinary readers.
 *
 * == Why this exists ==
 *
 * Greylock Glass has agreed to host the plugin for the pilot on one condition:
 * it must never affect their normal readership. Without this class the promise
 * we could make was "we will leave the site defaults at zero, so nothing is
 * priced, so no gate appears" -- true, but it is inert *by configuration*. One
 * mistaken option, one per-post meta value saved by an editor experimenting
 * with the meta box, and a paying reader hits a login wall on a story they
 * already subscribe to.
 *
 * Demo mode makes it inert *by design*. When enabled, every reader-facing
 * behaviour of this plugin is suppressed unless the visitor has explicitly
 * opted in to the demonstration:
 *
 *   - no access gate, whatever the post's required_bits say
 *   - no price negotiation
 *   - no access events sent to the ALS
 *   - no RSL metadata in the page head
 *
 * A publisher can therefore install the plugin, leave it switched on, and know
 * that the only people who can possibly see it working are the ones holding
 * the key.
 *
 * == How a demonstrator opts in ==
 *
 * Append the key to any URL on the site:
 *
 *   https://example.org/some-story/?newshare_demo=<key>
 *
 * That sets a first-party cookie so the rest of the walkthrough behaves
 * normally without decorating every link. Appending `?newshare_demo=off`
 * clears it again.
 *
 * The cookie is deliberately NOT an authentication cookie -- it carries no
 * identity and grants no access. It only answers "is this visitor part of the
 * demonstration audience?", which is why it is not an exception to the
 * network's no-cookies rule (the anonymous article meter is the same kind of
 * client-side state).
 *
 * == Failure direction ==
 *
 * Every uncertain case resolves to "not a participant". A missing key, a
 * blank configured key, a mismatch, a malformed cookie: all mean the ordinary
 * reader is left alone. The worst outcome of a bug here should be that the
 * demo does not run, never that a real reader is gated.
 *
 * @package Newshare_Network
 * @since   0.2.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Demo_Mode {

	/**
	 * Query parameter a demonstrator appends to opt in.
	 */
	private const PARAM = 'newshare_demo';

	/**
	 * Cookie that remembers the opt-in for the rest of the session.
	 */
	private const COOKIE = 'newshare_demo';

	/**
	 * Value of the query parameter that clears the opt-in.
	 */
	private const OFF = 'off';

	/**
	 * Memoised answer for this request.
	 *
	 * Resolved once because it is consulted from several hooks (content
	 * filtering, logging, RSL) and must give all of them the same answer even
	 * if a cookie is set part-way through the request.
	 *
	 * @var bool|null
	 */
	private ?bool $participant = null;

	/**
	 * Whether demo mode is switched on for this site.
	 *
	 * Off by default, so an existing install upgrading to this version keeps
	 * behaving exactly as it did.
	 *
	 * @return bool
	 */
	public function is_enabled(): bool {
		return (bool) get_option( 'newshare_demo_mode', false );
	}

	/**
	 * The configured demonstration key, if any.
	 *
	 * @return string Empty string when unset.
	 */
	private function key(): string {
		return trim( (string) get_option( 'newshare_demo_key', '' ) );
	}

	/**
	 * Handle an opt-in or opt-out on the current request.
	 *
	 * Hooked early (``init``) so the cookie is set before any output, and so
	 * the rest of the request already sees the visitor as a participant.
	 */
	public function handle_optin(): void {
		if ( ! $this->is_enabled() || ! isset( $_GET[ self::PARAM ] ) ) {
			return;
		}

		$supplied = sanitize_text_field( wp_unslash( $_GET[ self::PARAM ] ) );

		if ( self::OFF === $supplied ) {
			$this->participant = false;
			if ( ! headers_sent() ) {
				setcookie( self::COOKIE, '', time() - DAY_IN_SECONDS, COOKIEPATH, COOKIE_DOMAIN, is_ssl(), true );
			}
			unset( $_COOKIE[ self::COOKIE ] );
			return;
		}

		if ( ! $this->matches( $supplied ) ) {
			return;
		}

		$this->participant = true;
		if ( ! headers_sent() ) {
			setcookie( self::COOKIE, $supplied, time() + DAY_IN_SECONDS, COOKIEPATH, COOKIE_DOMAIN, is_ssl(), true );
		}
		// So a later call in this same request agrees with this one.
		$_COOKIE[ self::COOKIE ] = $supplied;
	}

	/**
	 * Constant-time comparison against the configured key.
	 *
	 * A blank configured key never matches. Without that guard, switching demo
	 * mode on before setting a key would admit every visitor presenting an
	 * empty parameter -- the exact inversion of what this class is for.
	 *
	 * @param string $supplied Candidate key from the request.
	 * @return bool
	 */
	private function matches( string $supplied ): bool {
		$key = $this->key();
		if ( '' === $key || '' === $supplied ) {
			return false;
		}
		return hash_equals( $key, $supplied );
	}

	/**
	 * Whether the current visitor should see any Newshare behaviour at all.
	 *
	 * When demo mode is off this returns true for everyone, which is ordinary
	 * operation on our own demonstration sites.
	 *
	 * @return bool
	 */
	public function is_participant(): bool {
		if ( null !== $this->participant ) {
			return $this->participant;
		}

		if ( ! $this->is_enabled() ) {
			return $this->participant = true;
		}

		// Logged-in editors and administrators are always participants, so a
		// publisher can see what their readers would see without hunting for
		// the key.
		if ( current_user_can( 'edit_posts' ) ) {
			return $this->participant = true;
		}

		$cookie = isset( $_COOKIE[ self::COOKIE ] )
			? sanitize_text_field( wp_unslash( $_COOKIE[ self::COOKIE ] ) )
			: '';

		return $this->participant = $this->matches( $cookie );
	}

	/**
	 * Whether plugin behaviour must be suppressed for this visitor.
	 *
	 * The inverse of is_participant(), named so that call sites read as an
	 * early bail rather than a double negative.
	 *
	 * @return bool
	 */
	public function should_suppress(): bool {
		return ! $this->is_participant();
	}
}
