<?php
/**
 * Newshare Session Management.
 *
 * Provides helper methods to inspect the current user's network session state.
 * Network session data is stored in wp_usermeta — only opaque identifiers,
 * never PII.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Session {

	/**
	 * List of all newshare user meta keys.
	 *
	 * @var string[]
	 */
	private const META_KEYS = array(
		'newshare_network_user_id',
		'newshare_network_group_id',
		'newshare_home_base_id',
		'newshare_session_id',
		'newshare_markup_ratio',
		'newshare_session_expires',
	);

	/**
	 * Check if the current WordPress user is a network user.
	 *
	 * A user is a network user if they have a newshare_network_user_id
	 * stored in their user meta.
	 *
	 * @param int|null $user_id Optional. The user ID to check. Defaults to current user.
	 * @return bool True if the user has a network identity.
	 */
	public function is_network_user( ?int $user_id = null ): bool {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		if ( 0 === $user_id ) {
			return false;
		}

		$network_user_id = get_user_meta( $user_id, 'newshare_network_user_id', true );
		return ! empty( $network_user_id );
	}

	/**
	 * Check if the current user's network session is still valid.
	 *
	 * Compares the stored session expiration timestamp against the
	 * current time.
	 *
	 * @param int|null $user_id Optional. The user ID to check. Defaults to current user.
	 * @return bool True if the session has not expired.
	 */
	public function is_session_valid( ?int $user_id = null ): bool {
		if ( null === $user_id ) {
			$user_id = get_current_user_id();
		}

		if ( ! $this->is_network_user( $user_id ) ) {
			return false;
		}

		$expires = (int) get_user_meta( $user_id, 'newshare_session_expires', true );
		if ( 0 === $expires ) {
			return false;
		}

		return $expires > time();
	}

	/**
	 * Get all network claims for the current user.
	 *
	 * Returns an associative array of all newshare_* user meta values.
	 *
	 * @param int|null $user_id Optional. The user ID. Defaults to current user.
	 * @return array<string, mixed> Associative array of network claims.
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

	/**
	 * Clear all network session data for a user.
	 *
	 * Removes all newshare_* user meta entries. Called during logout
	 * or when a session is invalidated.
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

		foreach ( self::META_KEYS as $key ) {
			delete_user_meta( $user_id, $key );
		}
	}

	/**
	 * Get the user's network group ID (bitmask).
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
	 * Check if a user has a specific access bit set.
	 *
	 * @param int      $required_bits The bitmask to check against.
	 * @param int|null $user_id       Optional. The user ID. Defaults to current user.
	 * @return bool True if all required bits are set in the user's group ID.
	 */
	public function has_access_bits( int $required_bits, ?int $user_id = null ): bool {
		if ( 0 === $required_bits ) {
			return true;
		}

		$group_id = $this->get_network_group_id( $user_id );
		return ( $group_id & $required_bits ) === $required_bits;
	}
}
