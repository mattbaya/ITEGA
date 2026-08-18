<?php
/**
 * Plugin Name: Newshare Network
 * Plugin URI: https://github.com/mattbaya/ITEGA
 * Description: Federated identity and content access for the Newshare Network. Adds "Network Login" for cross-publisher SSO with privacy-preserving pseudonymous identifiers.
 * Version: 0.2.5
 * Requires PHP: 8.1
 * Requires at least: 6.0
 * Author: ITEGA / Newshare Network
 * License: GPL-2.0-or-later
 * Text Domain: newshare-network
 */

/**
 * Main Plugin Bootstrap File.
 *
 * This is the entry point for the Newshare Network WordPress plugin. It handles:
 *
 *   1. Defining plugin constants (version, paths, URLs).
 *   2. Loading Composer autoload (for firebase/php-jwt dependency).
 *   3. Including all plugin class files.
 *   4. Instantiating the main Newshare_Network singleton.
 *   5. Registering all WordPress hooks (actions and filters).
 *   6. Plugin activation/deactivation hooks.
 *
 * == Plugin Architecture ==
 *
 * The plugin is organized into six classes, each with a single responsibility:
 *
 *   - Newshare_Session: Session state management (stored in wp_usermeta).
 *   - Newshare_OIDC: OIDC Relying Party flow (authorize -> callback -> login).
 *   - Newshare_Access: Bitmask access control and content gating.
 *   - Newshare_RSL: JSON-LD metadata injection for content pricing/licensing.
 *   - Newshare_Logger: Fire-and-forget event logging to the ALS.
 *   - Newshare_Admin: Settings page in wp-admin.
 *
 * All classes are wired together in this file via the Newshare_Network singleton.
 *
 * @package Newshare_Network
 * @since   0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// =========================================================================
// Plugin Constants
// =========================================================================

define( 'NEWSHARE_VERSION', '0.2.5' );

/**
 * Role given to readers who arrive through the network.
 *
 * Deliberately not `subscriber`. A publisher's own subscriber role is theirs,
 * and plugins routinely add capabilities to it -- membership plugins, forums,
 * private-content plugins. A network reader inheriting those would be given
 * access on this site that nobody decided to give them, and the publisher
 * would have no way to see it had happened.
 *
 * This role holds exactly one capability, `read`. It is also what makes these
 * accounts visible as a group: a publisher can sort their users list by role
 * and see precisely which ones arrived through ITEGA.
 */
define( 'NEWSHARE_ROLE', 'newshare_guest' );
define( 'NEWSHARE_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'NEWSHARE_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'NEWSHARE_PLUGIN_BASENAME', plugin_basename( __FILE__ ) );

// =========================================================================
// Composer Autoload
// =========================================================================

/**
 * Autoload Composer dependencies if available.
 *
 * The plugin requires firebase/php-jwt for JWT validation in the OIDC flow.
 * If the vendor directory doesn't exist, the plugin will still load but
 * OIDC authentication will fail. The admin class shows a warning notice
 * when dependencies are missing.
 */
if ( file_exists( NEWSHARE_PLUGIN_DIR . 'vendor/autoload.php' ) ) {
	require_once NEWSHARE_PLUGIN_DIR . 'vendor/autoload.php';
}

// =========================================================================
// Class File Includes
// =========================================================================

/**
 * Load plugin class files.
 *
 * These are loaded in dependency order: Session first (no deps), then
 * classes that depend on Session (OIDC, Access, Logger), then standalone
 * classes (RSL, Admin).
 */
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-provisioning.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-demo-mode.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-session.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-oidc.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-pricing.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-access.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-rsl.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-logger.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-ai-agent.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-logout.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-status.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-updater.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-admin.php';

// =========================================================================
// Main Plugin Class
// =========================================================================

/**
 * Main plugin class (Singleton).
 *
 * Instantiates all component classes and registers all WordPress hooks.
 * Use Newshare_Network::get_instance() to access the singleton.
 */
final class Newshare_Network {

	/**
	 * Singleton instance.
	 *
	 * @var Newshare_Network|null
	 */
	private static ?Newshare_Network $instance = null;

	/** @var Newshare_OIDC    OIDC Relying Party handler. */
	private Newshare_OIDC    $oidc;

	/** @var Newshare_Access  Bitmask access control. */
	private Newshare_Access  $access;

	/** @var Newshare_RSL     JSON-LD metadata injection. */
	private Newshare_RSL     $rsl;

	/** @var Newshare_Logger  Fire-and-forget event logger. */
	private Newshare_Logger  $logger;

	/** @var Newshare_Admin   Admin settings page. */
	private Newshare_Admin   $admin;

	/** @var Newshare_Session Session state management. */
	private Newshare_Session $session;

	/**
	 * Demonstration-audience gate.
	 *
	 * Consulted by every reader-facing component. On a real publisher's site
	 * this is what keeps the plugin invisible to their actual readership.
	 *
	 * @var Newshare_Demo_Mode
	 */
	private Newshare_Demo_Mode $demo;

	/** @var Newshare_Pricing Price negotiation with the reader's home base. */
	private Newshare_Pricing $pricing;

	/** @var Newshare_AI_Agent Machine-to-machine handshake for AI answer engines. */
	private Newshare_AI_Agent $ai_agent;

	/** @var Newshare_Logout  Sign out of this publisher, or of the network. */
	private Newshare_Logout $logout;

	/**
	 * The network status badge.
	 *
	 * Tells a reader whether they are signed in to the network, on every page,
	 * regardless of what the theme does with WordPress's admin bar. Silent in
	 * demo mode.
	 */
	private Newshare_Status $status;

	/**
	 * Get the singleton instance.
	 *
	 * @return self
	 */
	public static function get_instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	/**
	 * Private constructor -- use get_instance().
	 *
	 * Instantiates all component classes (with dependency injection) and
	 * registers all WordPress hooks.
	 */
	private function __construct() {
		// Instantiate component classes. Session is created first because
		// OIDC, Access, and Logger all depend on it.
		// Demo mode first: every reader-facing component asks it whether this
		// visitor should see anything at all.
		$this->demo    = new Newshare_Demo_Mode();
		$this->session = new Newshare_Session();
		$this->oidc    = new Newshare_OIDC( $this->session );
		$this->pricing = new Newshare_Pricing( $this->session );
		$this->access  = new Newshare_Access( $this->session, $this->pricing, $this->demo );
		$this->rsl     = new Newshare_RSL( $this->demo );
		$this->logger  = new Newshare_Logger( $this->session, $this->demo );
		$this->ai_agent = new Newshare_AI_Agent( $this->logger );
		$this->logout  = new Newshare_Logout( $this->session, $this->demo );
		$this->admin   = new Newshare_Admin();

		$this->register_hooks();
	}

	/**
	 * Register all WordPress hooks (actions and filters).
	 *
	 * This is the central wiring point where all plugin behavior is connected
	 * to WordPress's event system.
	 */
	private function register_hooks(): void {
		// -- OIDC Authentication Flow --

		// Register the REST API callback endpoint for the OIDC flow.
		add_action( 'rest_api_init', array( $this->oidc, 'register_routes' ) );

		// Handle OIDC login initiation when the newshare_login query parameter is present.
		// Ahead of everything: the exchange fetches this while the plugin is
		// mid-provision, and a theme or redirect plugin answering first would
		// fail the check.
		add_action( 'parse_request', array( 'Newshare_Provisioning', 'serve_challenge' ), 0 );
		add_action( 'init', array( $this->demo, 'handle_optin' ), 1 );
		add_action( 'init', array( $this, 'maybe_initiate_login' ) );

		// Handle OIDC login finalization (sets auth cookie in a non-REST context).
		// This is the second step of the two-step redirect from handle_callback().
		add_action( 'init', array( $this->oidc, 'finalize_login' ) );

		// -- Session Lifecycle --

		// FIX (MAJOR): Clear network session data when the user logs out.
		// Previously, clear_network_session() was never called on logout,
		// which meant stale network claims could persist in user meta after
		// the user logged out of WordPress.
		add_action( 'wp_logout', array( $this->session, 'clear_network_session' ) );

		// Ask a network reader how far the sign-out should reach, and carry
		// out the answer. Runs before the theme so the choice page can render
		// on its own; ordinary WordPress users are untouched, since they never
		// signed in through the network in the first place.
		add_action( 'init', array( $this->logout, 'handle_request' ), 2 );

		// Always tell a reader where they stand. Suppressed entirely in
		// demo mode -- see Newshare_Status.
		$this->status = new Newshare_Status( $this->session, $this->demo );
		add_action( 'wp_footer', array( $this->status, 'render' ) );
		add_filter( 'logout_url', array( $this->logout, 'filter_logout_url' ), 10, 2 );

		// -- Login UI --

		// Add "Network Login" button below the standard WP login form.
		add_action( 'login_form', array( $this, 'render_login_button' ) );

		// -- Content Access Control --

		// Check content access on page load and log the event for settlement.
		add_action( 'template_redirect', array( $this, 'handle_template_redirect' ) );

		// Filter post content to show access gate when the user lacks permissions.
		add_filter( 'the_content', array( $this->access, 'filter_content' ) );

		// A purchase is not covered by the ordinary logging path, which only
		// runs when the reader's tier already granted access. Without this the
		// publisher never files the transactions it is owed for.
		add_action( 'newshare_content_purchased', array( $this->logger, 'log_purchase' ), 10, 2 );

		// -- Content Metadata --

		// Inject RSL JSON-LD metadata in <head> on single posts.
		add_action( 'wp_head', array( $this->rsl, 'inject_rsl_metadata' ) );

		// -- Admin Settings --

		// Add the settings page to the WordPress admin menu.
		add_action( 'admin_menu', array( $this->admin, 'add_settings_page' ) );

		// Register settings, sections, and fields with the Settings API.
		add_action( 'admin_init', array( $this->admin, 'register_settings' ) );

		// Show admin notice if Composer dependencies are missing.
		add_action( 'admin_notices', array( $this->admin, 'check_dependencies' ) );

		// -- Post Editor --

		// Add the Newshare Access Control meta box to the post editor.
		add_action( 'add_meta_boxes', array( $this->access, 'add_meta_box' ) );

		// Save per-post access control settings when the post is saved.
		add_action( 'save_post', array( $this->access, 'save_meta_box' ) );

		// -- Front-End Assets --

		// Enqueue CSS and JS for the front-end login button and access gate.
		add_action( 'wp_enqueue_scripts', array( $this, 'enqueue_assets' ) );

		// Enqueue CSS on the wp-login.php page for the "Network Login" button.
		add_action( 'login_enqueue_scripts', array( $this, 'enqueue_login_assets' ) );
	}

	// =========================================================================
	// Content Access + Logging
	// =========================================================================

	/**
	 * Handle template_redirect: log content access when access is granted.
	 *
	 * When a network user views a single post and access is granted, log the
	 * event to the ALS for settlement (revenue sharing). This runs on every
	 * page load but only fires for network users viewing single posts.
	 *
	 * Hooked to: template_redirect
	 */
	public function handle_template_redirect(): void {
		if ( ! is_singular( 'post' ) ) {
			return;
		}

		$post_id = get_the_ID();
		if ( ! $post_id ) {
			return;
		}

		// -----------------------------------------------------------------
		// Machine callers are handled first and separately. An AI answer
		// engine cannot follow a redirect or complete a login, so it must
		// never reach the reader access gate -- it would be handed an HTML
		// page describing a login it cannot perform. The handshake either
		// answers the request itself (402, 403) or clears the request to be
		// served, having already filed its own log report.
		// -----------------------------------------------------------------
		if ( $this->ai_agent->is_agent_request() ) {
			$this->ai_agent->handle( $post_id );
			return;
		}

		// Only log if the user has access AND is a network user.
		// Anonymous users and local-only WP users are not logged.
		if ( $this->access->check_access( $post_id ) && $this->session->is_network_user() ) {
			$this->logger->log_content_access( $post_id );
		}
	}

	// =========================================================================
	// Login UI
	// =========================================================================

	/**
	 * Render the Network Login button on the WP login form.
	 *
	 * Adds a "Log in with your news network account" button below the standard
	 * WordPress username/password form on wp-login.php.
	 *
	 * Hooked to: login_form
	 */
	public function render_login_button(): void {
		include NEWSHARE_PLUGIN_DIR . 'templates/network-login-button.php';
	}

	// =========================================================================
	// OIDC Login Initiation
	// =========================================================================

	/**
	 * Initiate OIDC login when the newshare_login query parameter is present.
	 *
	 * This is triggered by clicking the "Network Login" button (either on the
	 * access gate or on the wp-login.php page). The nonce check prevents CSRF.
	 *
	 * The return_to parameter captures the article URL so the user is redirected
	 * back to the article they were reading after authentication.
	 *
	 * Hooked to: init
	 */
	public function maybe_initiate_login(): void {
		if ( isset( $_GET['newshare_login'] ) && '1' === $_GET['newshare_login'] ) {
			check_admin_referer( 'newshare_login_initiate', 'newshare_nonce' );

			// Capture the return URL if provided (from the access gate template).
			$return_to = isset( $_GET['newshare_return_to'] )
				? esc_url_raw( wp_unslash( $_GET['newshare_return_to'] ) )
				: null;

			$this->oidc->initiate_login( $return_to );
		}
	}

	// =========================================================================
	// Front-End Assets
	// =========================================================================

	/**
	 * Enqueue front-end styles and scripts.
	 *
	 * Loads the CSS for the access gate and login button, and the JS for
	 * any interactive login functionality.
	 *
	 * Hooked to: wp_enqueue_scripts
	 */
	public function enqueue_assets(): void {
		// Nothing at all when demo mode is suppressing this visitor. Two asset
		// URLs in the page source name the plugin, and cost two HTTP requests,
		// on a site whose owner was promised their ordinary readers would see
		// no trace of it. Behaviour was already suppressed; this is the last
		// fingerprint, and it was visible on greylockglass.com within hours of
		// them installing it.
		if ( $this->demo->should_suppress() ) {
			return;
		}

		wp_enqueue_style(
			'newshare-login',
			NEWSHARE_PLUGIN_URL . 'assets/css/newshare-login.css',
			array(),
			NEWSHARE_VERSION
		);
		wp_enqueue_script(
			'newshare-login',
			NEWSHARE_PLUGIN_URL . 'assets/js/newshare-login.js',
			array(),
			NEWSHARE_VERSION,
			true
		);
	}

	/**
	 * Enqueue styles on the wp-login.php page.
	 *
	 * Loads the CSS for the "Network Login" button that appears below the
	 * standard WordPress login form.
	 *
	 * Hooked to: login_enqueue_scripts
	 */
	public function enqueue_login_assets(): void {
		wp_enqueue_style(
			'newshare-login',
			NEWSHARE_PLUGIN_URL . 'assets/css/newshare-login.css',
			array(),
			NEWSHARE_VERSION
		);
	}
}

// =========================================================================
// Activation / Deactivation Hooks
// =========================================================================

/**
 * Activation hook -- set default options.
 *
 * Populates all plugin options with sensible defaults on first activation.
 * Uses add_option() (not update_option()) so existing values are preserved
 * if the plugin is deactivated and reactivated.
 */
/**
 * Create the network reader role, if it is not already there.
 *
 * Called on activation and again on init, because a role lives in the
 * database rather than in code: a site restored from a backup taken before
 * this version, or one where the activation hook did not run, would otherwise
 * have the plugin assigning a role that does not exist -- which WordPress
 * accepts silently, leaving the reader with no capabilities at all.
 */
function newshare_register_role(): void {
	if ( ! get_role( NEWSHARE_ROLE ) ) {
		add_role(
			NEWSHARE_ROLE,
			__( 'ITEGA Guest', 'newshare-network' ),
			array( 'read' => true )
		);
	}
}
add_action( 'init', 'newshare_register_role', 0 );

/**
 * Move readers this plugin created onto the new role, once.
 *
 * Scoped as tightly as it can be: only accounts carrying this plugin's own
 * meta key, and only those still holding the role we used to assign. A
 * publisher's own subscribers are never touched, and neither is any account
 * whose role someone has since changed on purpose.
 *
 * Guarded by an option so it runs once rather than on every request.
 */
function newshare_migrate_reader_roles(): void {
	if ( get_option( 'newshare_role_migrated' ) ) {
		return;
	}
	update_option( 'newshare_role_migrated', '1' );

	if ( ! get_role( NEWSHARE_ROLE ) ) {
		return;
	}

	$readers = get_users(
		array(
			'meta_key'     => 'newshare_network_user_id',
			'meta_compare' => 'EXISTS',
			'role'         => 'subscriber',
			'fields'       => 'ID',
			'number'       => 500,
		)
	);

	foreach ( $readers as $id ) {
		$user = get_userdata( $id );
		// Only if subscriber is their *only* role -- an account someone has
		// also made an editor is not ours to demote.
		if ( $user instanceof WP_User && array( 'subscriber' ) === $user->roles ) {
			$user->set_role( NEWSHARE_ROLE );
		}
	}
}
add_action( 'init', 'newshare_migrate_reader_roles', 1 );


function newshare_activate(): void {
	newshare_register_role();
	// Network-level defaults. These are the live ITEGA services and are the
	// same for every publisher, so there is no reason to make each site's
	// operator retype them -- and a typo here fails in ways that look like a
	// broken network rather than a wrong setting.
	$defaults = array(
		'newshare_pub_mbr_id'            => '',
		'newshare_als_auth_endpoint'     => 'https://als.itega.org',
		'newshare_als_logging_endpoint'  => 'https://als.itega.org/log',
		'newshare_discovery_endpoint'    => 'https://network.itega.org',
		'newshare_als_public_key_url'    => 'https://als.itega.org/.well-known/jwks.json',
		'newshare_als_api_key'           => '',
		'newshare_default_page_class'    => '0.05',
		'newshare_premium_page_class'    => '0.20',
		'newshare_minimum_page_class'    => '0.02',
		'newshare_posted_price_is_final' => '',
		'newshare_default_required_bits' => '0',
		'newshare_default_rsl_tag'       => 'CC-BY-NC',
		'newshare_free_article_count'    => '3',
		// Tell anonymous readers they are not signed in. Off by default: on a
		// live newspaper that is a visible change to every reader. Our
		// demonstration sites turn it on, because a tester who cannot tell
		// whether they are signed in reports the paywall as broken.
		'newshare_status_badge_anonymous' => '',
	);

	// Per-site values -- the publisher's own member ID and the shared API key
	// -- come from a provisioning file written when the distributable is built
	// for a particular publisher, or from constants in wp-config.php. Both are
	// optional: without either, the plugin simply starts unconfigured and the
	// settings page is filled in by hand as before.
	$provision = __DIR__ . '/newshare-config.php';
	if ( is_readable( $provision ) ) {
		$supplied = include $provision;
		if ( is_array( $supplied ) ) {
			$defaults = array_merge( $defaults, $supplied );
		}
	}

	// wp-config.php constants win over everything, so an operator can override
	// a baked value without repackaging.
	foreach ( array(
		'NEWSHARE_PUB_MBR_ID'    => 'newshare_pub_mbr_id',
		'NEWSHARE_ALS_API_KEY'   => 'newshare_als_api_key',
		'NEWSHARE_ALS_AUTH_URL'  => 'newshare_als_auth_endpoint',
		'NEWSHARE_DISCOVERY_URL' => 'newshare_discovery_endpoint',
	) as $constant => $option ) {
		if ( defined( $constant ) ) {
			$defaults[ $option ] = constant( $constant );
		}
	}

	// add_option, not update_option: a site that has already been configured
	// keeps its settings when the plugin is reactivated or upgraded.
	foreach ( $defaults as $key => $value ) {
		if ( false === get_option( $key ) ) {
			add_option( $key, $value );
		}
	}

	// Fetch this site's own credentials a few seconds from now. See
	// newshare_maybe_provision() for why this is not done inline.
	if ( ! wp_next_scheduled( 'newshare_provision_event' ) ) {
		wp_schedule_single_event( time() + 5, 'newshare_provision_event' );
	}
}
/**
 * Ask ITEGA for this site's credentials, shortly after activation.
 *
 * Scheduled rather than run inside the activation hook: activation happens
 * during the plugin-upload request, and this call waits on the exchange
 * fetching a URL back from this site. A stall there would look to the
 * publisher like a broken install, and WordPress would have no way to say
 * otherwise.
 */
function newshare_maybe_provision(): void {
	if ( Newshare_Provisioning::is_configured() ) {
		return;
	}
	Newshare_Provisioning::provision();
}
add_action( 'newshare_provision_event', 'newshare_maybe_provision' );

/**
 * Offer updates from ITEGA through WordPress's own update machinery.
 *
 * Registered unconditionally and outside the reader-facing class: it runs in
 * the admin, it is nothing to do with demo mode, and a publisher must hear
 * about a fix whether or not they have switched anything on.
 */
function newshare_register_updater(): void {
	( new Newshare_Updater( NEWSHARE_PLUGIN_BASENAME ) )->register();
}
add_action( 'admin_init', 'newshare_register_updater' );
add_action( 'wp_version_check', 'newshare_register_updater' );

register_activation_hook( __FILE__, 'newshare_activate' );

/**
 * Deactivation hook -- cleanup transients.
 *
 * Removes cached OIDC configuration and public keys. Settings are NOT
 * deleted on deactivation (only on uninstall) so they persist if the
 * plugin is reactivated.
 */
function newshare_deactivate(): void {
	delete_transient( 'newshare_als_public_key' );
	delete_transient( 'newshare_als_oidc_config' );
}
register_deactivation_hook( __FILE__, 'newshare_deactivate' );

// =========================================================================
// Plugin Initialization
// =========================================================================

/**
 * Initialize the plugin on plugins_loaded.
 *
 * Uses plugins_loaded (priority 10) to ensure WordPress core and all
 * dependencies are available before the plugin initializes.
 *
 * @return Newshare_Network The singleton instance.
 */
function newshare_network_init(): Newshare_Network {
	return Newshare_Network::get_instance();
}
add_action( 'plugins_loaded', 'newshare_network_init' );
