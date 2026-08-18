<?php
/**
 * Uninstall: leave the publisher's site as we found it.
 *
 * Runs only when the plugin is deleted, never on deactivation -- a publisher
 * switching it off for an afternoon keeps their settings and their readers.
 *
 * What this deliberately does NOT do is delete the guest accounts. They are
 * the publisher's records now: they may have left comments, and a site owner
 * is better placed than an uninstaller to decide whether an account with
 * history attached should disappear. The role is removed, so any remaining
 * accounts fall back to no role at all and can be found and dealt with in one
 * pass from the users screen.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}

// Settings, including the issued credentials.
foreach ( array(
	'newshare_pub_mbr_id',
	'newshare_als_api_key',
	'newshare_als_auth_endpoint',
	'newshare_als_logging_endpoint',
	'newshare_als_public_key_url',
	'newshare_als_client_id',
	'newshare_discovery_endpoint',
	'newshare_default_page_class',
	'newshare_premium_page_class',
	'newshare_minimum_page_class',
	'newshare_posted_price_is_final',
	'newshare_default_required_bits',
	'newshare_default_rsl_tag',
	'newshare_free_article_count',
	'newshare_demo_mode',
	'newshare_demo_key',
	'newshare_provisioning_status',
	'newshare_provisioning_nonce',
) as $option ) {
	delete_option( $option );
}

// The role we added, and nothing else. A publisher's own roles are theirs.
if ( get_role( 'newshare_guest' ) ) {
	remove_role( 'newshare_guest' );
}

// Any scheduled provisioning attempt that never ran.
$timestamp = wp_next_scheduled( 'newshare_provision_event' );
if ( $timestamp ) {
	wp_unschedule_event( $timestamp, 'newshare_provision_event' );
}
