<?php
/**
 * Plugin Name: Newshare Network
 * Plugin URI: https://github.com/mattbaya/ITEGA
 * Description: Federated identity and content access for the Newshare Network. Adds "Network Login" for cross-publisher SSO with privacy-preserving pseudonymous identifiers.
 * Version: 0.1.0
 * Requires PHP: 8.1
 * Requires at least: 6.0
 * Author: ITEGA / Newshare Network
 * License: GPL-2.0-or-later
 * Text Domain: newshare-network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'NEWSHARE_VERSION', '0.1.0' );
define( 'NEWSHARE_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'NEWSHARE_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'NEWSHARE_PLUGIN_BASENAME', plugin_basename( __FILE__ ) );

/**
 * Autoload Composer dependencies if available.
 */
if ( file_exists( NEWSHARE_PLUGIN_DIR . 'vendor/autoload.php' ) ) {
	require_once NEWSHARE_PLUGIN_DIR . 'vendor/autoload.php';
}

/**
 * Load plugin class files.
 */
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-session.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-oidc.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-access.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-rsl.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-logger.php';
require_once NEWSHARE_PLUGIN_DIR . 'includes/class-newshare-admin.php';

/**
 * Main plugin class.
 */
final class Newshare_Network {

	/**
	 * Singleton instance.
	 *
	 * @var Newshare_Network|null
	 */
	private static ?Newshare_Network $instance = null;

	private Newshare_OIDC    $oidc;
	private Newshare_Access  $access;
	private Newshare_RSL     $rsl;
	private Newshare_Logger  $logger;
	private Newshare_Admin   $admin;
	private Newshare_Session $session;

	/**
	 * Get the singleton instance.
	 */
	public static function get_instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	/**
	 * Private constructor — use get_instance().
	 */
	private function __construct() {
		$this->session = new Newshare_Session();
		$this->oidc    = new Newshare_OIDC( $this->session );
		$this->access  = new Newshare_Access( $this->session );
		$this->rsl     = new Newshare_RSL();
		$this->logger  = new Newshare_Logger( $this->session );
		$this->admin   = new Newshare_Admin();

		$this->register_hooks();
	}

	/**
	 * Register all WordPress hooks.
	 */
	private function register_hooks(): void {
		// REST API route for OIDC callback.
		add_action( 'rest_api_init', array( $this->oidc, 'register_routes' ) );

		// Add "Network Login" button below the standard WP login form.
		add_action( 'login_form', array( $this, 'render_login_button' ) );

		// Check content access on page load and log the event.
		add_action( 'template_redirect', array( $this, 'handle_template_redirect' ) );

		// Inject RSL JSON-LD metadata in <head> on single posts.
		add_action( 'wp_head', array( $this->rsl, 'inject_rsl_metadata' ) );

		// Filter post content to show access gate when needed.
		add_filter( 'the_content', array( $this->access, 'filter_content' ) );

		// Admin settings page.
		add_action( 'admin_menu', array( $this->admin, 'add_settings_page' ) );
		add_action( 'admin_init', array( $this->admin, 'register_settings' ) );

		// Post editor meta box for access control.
		add_action( 'add_meta_boxes', array( $this->access, 'add_meta_box' ) );
		add_action( 'save_post', array( $this->access, 'save_meta_box' ) );

		// Enqueue front-end assets.
		add_action( 'wp_enqueue_scripts', array( $this, 'enqueue_assets' ) );
		add_action( 'login_enqueue_scripts', array( $this, 'enqueue_login_assets' ) );

		// OIDC login initiation via query parameter.
		add_action( 'init', array( $this, 'maybe_initiate_login' ) );
	}

	/**
	 * Handle template_redirect: log content access when granted.
	 */
	public function handle_template_redirect(): void {
		if ( ! is_singular( 'post' ) ) {
			return;
		}

		$post_id = get_the_ID();
		if ( ! $post_id ) {
			return;
		}

		if ( $this->access->check_access( $post_id ) && $this->session->is_network_user() ) {
			$this->logger->log_content_access( $post_id );
		}
	}

	/**
	 * Render the Network Login button on the WP login form.
	 */
	public function render_login_button(): void {
		include NEWSHARE_PLUGIN_DIR . 'templates/network-login-button.php';
	}

	/**
	 * Initiate OIDC login when the newshare_login query parameter is present.
	 */
	public function maybe_initiate_login(): void {
		if ( isset( $_GET['newshare_login'] ) && '1' === $_GET['newshare_login'] ) {
			check_admin_referer( 'newshare_login_initiate', 'newshare_nonce' );
			$this->oidc->initiate_login();
		}
	}

	/**
	 * Enqueue front-end styles and scripts.
	 */
	public function enqueue_assets(): void {
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
	 * Enqueue styles on the login page.
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

/**
 * Activation hook — set default options.
 */
function newshare_activate(): void {
	$defaults = array(
		'newshare_pub_mbr_id'            => '',
		'newshare_als_auth_endpoint'     => 'https://als.newshare.example/auth',
		'newshare_als_logging_endpoint'  => 'https://als.newshare.example/log',
		'newshare_als_api_key'           => '',
		'newshare_als_public_key_url'    => '',
		'newshare_default_page_class'    => '0.05',
		'newshare_premium_page_class'    => '0.15',
		'newshare_default_required_bits' => '0',
		'newshare_default_rsl_tag'       => 'CC-BY-NC',
		'newshare_free_article_count'    => '3',
	);

	foreach ( $defaults as $key => $value ) {
		if ( false === get_option( $key ) ) {
			add_option( $key, $value );
		}
	}
}
register_activation_hook( __FILE__, 'newshare_activate' );

/**
 * Deactivation hook — cleanup transients.
 */
function newshare_deactivate(): void {
	delete_transient( 'newshare_als_public_key' );
	delete_transient( 'newshare_als_oidc_config' );
}
register_deactivation_hook( __FILE__, 'newshare_deactivate' );

/**
 * Initialize the plugin.
 */
function newshare_network_init(): Newshare_Network {
	return Newshare_Network::get_instance();
}
add_action( 'plugins_loaded', 'newshare_network_init' );
