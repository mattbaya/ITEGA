<?php
/**
 * Newshare Session Management.
 *
 * Provides helper methods to inspect and manage the current user's network
 * session state. This class is the single source of truth for "is this user
 * authenticated via the Newshare Network?" within the WordPress context.
 *
 * == Session Storage Approach ==
 *
 * Network session data is stored in WordPress user meta (wp_usermeta), NOT in
 * cookies or PHP sessions. This approach was chosen because:
 *
 *   1. The Newshare Network protocol prohibits authentication cookies -- auth
 *      state is passed via HTTP headers and signed JWT tokens.
 *   2. wp_usermeta is persistent across page loads and reliable in all WordPress
 *      contexts (front-end, REST API, admin, cron).
 *   3. WordPress already handles user identification via its own auth cookies,
 *      so we piggyback on that for session lookup.
 *   4. User meta survives WordPress cache clears and plugin restarts.
 *
 * == Stored Claims (All Opaque, No PII) ==
 *
 * The following keys are stored in user meta during OIDC callback:
 *
 *   - newshare_network_user_id: PPID (Pairwise Pseudonymous Identifier) --
 *     a unique opaque ID for this user at THIS publisher. Different publishers
 *     get different PPIDs for the same user, preventing cross-site correlation.
 *
 *   - newshare_network_group_id: NetworkGroupId bitmask encoding the user's
 *     subscription tiers (e.g., 4096 = Paid, 8 = Digital, etc.).
 *
 *   - newshare_home_base_id: Identifies which home base (IdSP) authenticated
 *     the user. Used for logging and settlement routing.
 *
 *   - newshare_session_id: Opaque session reference from the ALS, used to
 *     correlate events within a single login session.
 *
 *   - newshare_markup_ratio: The home base's retail markup multiplier, applied
 *     on top of the publisher's wholesale pageClass price.
 *
 *   - newshare_session_expires: Unix timestamp when the session JWT expires.
 *     After this time, the user must re-authenticate.
 *
 * == Session Lifecycle ==
 *
 *   1. Created: During OIDC callback (class-newshare-oidc.php) when a user
 *      successfully authenticates through the ALS.
 *   2. Read: By access control (class-newshare-access.php) and logging
 *      (class-newshare-logger.php) to check permissions and build event data.
 *   3. Cleared: On WordPress logout (wp_logout action) via clear_network_session().
 *
 * @package Newshare_Network
 * @since   0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Session {

	/**
	 * List of all Newshare user meta keys.
	 *
	 * These are the keys stored in wp_usermeta during the OIDC callback.
	 * All values are opaque identifiers or numeric settings -- no PII
	 * (Personally Identifiable Information) is ever stored.
	 *
	 * @var string[]
	 */
	private const META_KEYS = array(
		'newshare_network_user_id',    // PPID: opaque, unique per publisher.
		'newshare_network_group_id',   // Bitmask: subscription tier encoding.
		'newshare_home_base_id',       // Opaque: which home base authenticated the user.
		'newshare_session_id',         // Opaque: session reference for event correlation.
		'newshare_markup_ratio',       // Float: home base retail markup multiplier.
		'newshare_session_expires',    // Unix timestamp: when the JWT session expires.
	);

	// =========================================================================
	// Session Status Checks
	// =========================================================================

	/**
	 * Check if the current WordPress user is a network user.
	 *
	 * A user is a "network user" if they have a newshare_network_user_id
	 * stored in their user meta -- meaning they have previously authenticated
	 * through the Newshare Network OIDC flow.
	 *
	 * Note: This does NOT check session validity (expiration). Use
	 * is_session_valid() for that.
	 *
	 * @param int|null $user_id Optional. The user ID to check. Defaults to current user.
	 * @return bool True if the user has a network identity.
	 */
	public function is_network_user( ?int $user_id = null ): bool {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		// User ID 0 means no user is logged in.
		if ( 0 === $user_id ) {
			return false;
		}

		$network_user_id = get_user_meta( $user_id, 'newshare_network_user_id', true );
		return ! empty( $network_user_id );
	}

	/**
	 * Check if the current user's network session is still valid (not expired).
	 *
	 * Compares the stored session expiration timestamp (from the JWT exp claim)
	 * against the current server time. If the session has expired, the user
	 * needs to re-authenticate through the OIDC flow.
	 *
	 * @param int|null $user_id Optional. The user ID to check. Defaults to current user.
	 * @return bool True if the session has not expired.
	 */
	public function is_session_valid( ?int $user_id = null ): bool {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		// Must be a network user to have a valid session.
		if ( ! $this->is_network_user( $user_id ) ) {
			return false;
		}

		// Check the expiration timestamp from the JWT exp claim.
		$expires = (int) get_user_meta( $user_id, 'newshare_session_expires', true );
		if ( 0 === $expires ) {
			return false;
		}

		return $expires > time();
	}

	// =========================================================================
	// Claims Retrieval
	// =========================================================================

	/**
	 * Get all network claims for the current user.
	 *
	 * Returns an associative array of all newshare_* user meta values.
	 * Used by the logger (class-newshare-logger.php) to build event payloads
	 * and by access control (class-newshare-access.php) for bitmask checks.
	 *
	 * @param int|null $user_id Optional. The user ID. Defaults to current user.
	 * @return array<string, mixed> Associative array of network claims keyed by meta key.
	 */
	public function get_network_claims( ?int $user_id = null ): array {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		if ( 0 === $user_id ) {
			return array();
		}

		$claims = array();
		foreach ( self::META_KEYS as $key ) {
			$claims[ $key ] = get_user_meta( $user_id, $key, true );
		}

		return $claims;
	}

	// =========================================================================
	// Session Cleanup
	// =========================================================================

	/**
	 * Clear all network session data for a user.
	 *
	 * Removes all newshare_* user meta entries. This is called:
	 *   - When the user logs out of WordPress (wp_logout action).
	 *   - When a session is explicitly invalidated.
	 *
	 * After clearing, is_network_user() will return false for this user
	 * until they re-authenticate through the OIDC flow.
	 *
	 * Note: This method accepts either a user ID (int) or no arguments
	 * (defaults to current user). When called from the wp_logout action,
	 * WordPress passes the user ID as the first argument.
	 *
	 * @param int|null $user_id Optional. The user ID. Defaults to current user.
	 */
	public function clear_network_session( ?int $user_id = null ): void {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		if ( 0 === $user_id ) {
			return;
		}

		// Remove all Newshare-related user meta entries.
		foreach ( self::META_KEYS as $key ) {
			delete_user_meta( $user_id, $key );
		}
	}

	// =========================================================================
	// Convenience Accessors
	// =========================================================================

	/**
	 * Get the user's network group ID (bitmask).
	 *
	 * Convenience method for reading just the NetworkGroupId bitmask,
	 * which encodes the user's subscription tiers. Used by
	 * Newshare_Session::has_access_bits() and can be used by themes
	 * for conditional content display.
	 *
	 * @param int|null $user_id Optional. The user ID. Defaults to current user.
	 * @return int The network group bitmask, or 0 if not set.
	 */
	public function get_network_group_id( ?int $user_id = null ): int {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		return (int) get_user_meta( $user_id, 'newshare_network_group_id', true );
	}

	/**
	 * Check if a user has a specific access bit set in their NetworkGroupId.
	 *
	 * Uses bitwise AND to check if ALL required bits are present in the
	 * user's group ID. This is the same check used by Newshare_Access::check_access()
	 * but exposed as a public helper for use by themes and other plugins.
	 *
	 * Example: has_access_bits(4104) checks for Paid (4096) + Digital (8).
	 *
	 * @param int      $required_bits The bitmask to check against.
	 * @param int|null $user_id       Optional. The user ID. Defaults to current user.
	 * @return bool True if all required bits are set in the user's group ID.
	 */
	public function has_access_bits( int $required_bits, ?int $user_id = null ): bool {
		// Zero bits = free content, always accessible.
		if ( 0 === $required_bits ) {
			return true;
		}

		$group_id = $this->get_network_group_id( $user_id );
		return ( $group_id & $required_bits ) === $required_bits;
	}
}
