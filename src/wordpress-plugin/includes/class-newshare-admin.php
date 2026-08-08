<?php
/**
 * Newshare Admin Settings Page.
 *
 * Provides the Settings > Newshare Network admin page where publishers configure
 * their network integration. This is the primary configuration interface for
 * site administrators.
 *
 * == Settings Sections ==
 *
 * 1. **Network Identity** -- Publisher Member ID (pubMbrId), the unique identifier
 *    assigned to this publisher when they joined the Newshare Network.
 *
 * 2. **ALS Endpoints** -- URLs for the ALS (Auth/Logging/Settlement) services:
 *    - Auth URL: Where OIDC authorization requests are sent.
 *    - Logging URL: Where content access events are POSTed.
 *    - API Key: Authenticates this publisher to the ALS.
 *    - JWKS URL: Optional override for the JWT public key endpoint.
 *
 * 3. **Content Pricing** -- Default wholesale prices (pageClass) for standard
 *    and premium content. Individual posts can override these values via the
 *    Newshare Access Control meta box in the post editor.
 *
 * 4. **Access Control** -- Default subscription tier requirement and the
 *    anonymous article meter limit (how many gated articles non-logged-in
 *    users can read before being prompted to log in).
 *
 * 5. **RSL Defaults** -- Default content license tag (e.g., CC-BY-NC) applied
 *    to all posts unless overridden per-post.
 *
 * == Connection Test ==
 *
 * A "Test Connection" button at the bottom of the settings page verifies that
 * the plugin can reach the ALS by fetching the list of registered home bases.
 *
 * @package Newshare_Network
 * @since   0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Admin {

	// =========================================================================
	// Composer Dependency Check
	// =========================================================================

	/**
	 * Check if required Composer dependencies are available and show an admin
	 * notice if they are not.
	 *
	 * The plugin requires firebase/php-jwt for JWT validation in the OIDC flow.
	 * If Composer autoload has not been run, the JWT classes won't be available
	 * and the OIDC callback will fail at runtime.
	 *
	 * Hooked to: admin_notices
	 */
	public function check_dependencies(): void {
		// Check if firebase/php-jwt is available (loaded via Composer autoload).
		if ( ! class_exists( '\Firebase\JWT\JWT' ) ) {
			echo '<div class="notice notice-error"><p>';
			echo '<strong>' . esc_html__( 'Newshare Network:', 'newshare-network' ) . '</strong> ';
			echo esc_html__(
				'Required Composer dependencies are missing. Please run "composer install" in the plugin directory to install firebase/php-jwt and other dependencies. The OIDC login flow will not work until dependencies are installed.',
				'newshare-network'
			);
			echo '</p><p><code>cd ' . esc_html( NEWSHARE_PLUGIN_DIR ) . ' && composer install</code></p>';
			echo '</div>';
		}
	}

	// =========================================================================
	// Settings Page Registration
	// =========================================================================

	/**
	 * Add the settings page under the Settings menu.
	 *
	 * Creates a "Newshare Network" entry under Settings in the WordPress
	 * admin sidebar. Requires the manage_options capability (administrator).
	 *
	 * Hooked to: admin_menu
	 */
	public function add_settings_page(): void {
		add_options_page(
			__( 'Newshare Network Settings', 'newshare-network' ),
			__( 'Newshare Network', 'newshare-network' ),
			'manage_options',
			'newshare-network',
			array( $this, 'render_settings_page' )
		);
	}

	// =========================================================================
	// Settings Registration (Settings API)
	// =========================================================================

	/**
	 * Register all settings, sections, and fields using the WordPress Settings API.
	 *
	 * This method defines the complete settings schema for the plugin. Each
	 * setting is registered with a sanitization callback and grouped into
	 * logical sections.
	 *
	 * Hooked to: admin_init
	 */
	public function register_settings(): void {
		// -----------------------------------------------------------------
		// Section 1: Network Identity
		// The publisher's unique identifier in the Newshare Network.
		// This is assigned when the publisher joins the network (e.g., PUB003).
		// -----------------------------------------------------------------
		add_settings_section(
			'newshare_identity',
			__( 'Network Identity', 'newshare-network' ),
			array( $this, 'render_identity_section' ),
			'newshare-network'
		);

		$this->add_text_field(
			'newshare_pub_mbr_id',
			__( 'Publisher Member ID', 'newshare-network' ),
			'newshare_identity',
			__( 'Your unique publisher identifier in the network (e.g., PUB003).', 'newshare-network' )
		);

		// -----------------------------------------------------------------
		// Section 2: ALS Endpoints
		// URLs and credentials for communicating with the ALS
		// (Auth/Logging/Settlement) infrastructure. The OIDC flow goes
		// through the ALS, not directly to Keycloak.
		// -----------------------------------------------------------------
		add_settings_section(
			'newshare_endpoints',
			__( 'ALS Endpoints', 'newshare-network' ),
			array( $this, 'render_endpoints_section' ),
			'newshare-network'
		);

		$this->add_text_field(
			'newshare_als_auth_endpoint',
			__( 'ALS Auth URL', 'newshare-network' ),
			'newshare_endpoints',
			__( 'The ALS authentication endpoint (e.g., https://als.newshare.example/auth).', 'newshare-network' ),
			'url'
		);

		$this->add_text_field(
			'newshare_als_logging_endpoint',
			__( 'ALS Logging URL', 'newshare-network' ),
			'newshare_endpoints',
			__( 'The ALS event logging endpoint (e.g., https://als.newshare.example/log).', 'newshare-network' ),
			'url'
		);

		$this->add_text_field(
			'newshare_discovery_endpoint',
			__( 'Network Discovery URL', 'newshare-network' ),
			'newshare_endpoints',
			__(
				'ITEGA network directory (e.g., https://network.itega.example). Used to find a visiting reader\'s home base and its buying agent.',
				'newshare-network'
			),
			'url'
		);

		$this->add_text_field(
			'newshare_als_api_key',
			__( 'ALS API Key', 'newshare-network' ),
			'newshare_endpoints',
			__( 'API key for authenticating with the ALS logging service.', 'newshare-network' ),
			'password'
		);

		$this->add_text_field(
			'newshare_als_public_key_url',
			__( 'ALS JWKS URL', 'newshare-network' ),
			'newshare_endpoints',
			__( 'Override URL for the ALS JWKS endpoint. Leave blank to auto-discover from OIDC configuration.', 'newshare-network' ),
			'url'
		);

		// -----------------------------------------------------------------
		// Section 3: Content Pricing
		// Wholesale prices (pageClass) for content. The home base applies
		// its markupRatio to calculate the retail price charged to the user.
		// Publishers set the wholesale price; home bases set the retail markup.
		// -----------------------------------------------------------------
		add_settings_section(
			'newshare_pricing',
			__( 'Content Pricing', 'newshare-network' ),
			array( $this, 'render_pricing_section' ),
			'newshare-network'
		);

		$this->add_number_field(
			'newshare_default_page_class',
			__( 'Default Page Class', 'newshare-network' ),
			'newshare_pricing',
			__( 'Default wholesale price for content (e.g., 0.05).', 'newshare-network' ),
			'0.01',
			'0'
		);

		$this->add_number_field(
			'newshare_premium_page_class',
			__( 'Premium Page Class', 'newshare-network' ),
			'newshare_pricing',
			__( 'Wholesale price for premium content (e.g., 0.15).', 'newshare-network' ),
			'0.01',
			'0'
		);

		// -----------------------------------------------------------------
		// Section 4: Access Control
		// Default subscription tier and anonymous meter settings.
		// The tier uses NetworkGroupId bitmask values (see class-newshare-access.php).
		// The free article meter lets anonymous users read a limited number
		// of gated articles before being prompted to log in.
		// -----------------------------------------------------------------
		add_settings_section(
			'newshare_access',
			__( 'Access Control', 'newshare-network' ),
			array( $this, 'render_access_section' ),
			'newshare-network'
		);

		// Default required bits -- uses a select field with predefined tier values.
		register_setting( 'newshare-network', 'newshare_default_required_bits', array(
			'type'              => 'integer',
			'sanitize_callback' => 'absint',
			'default'           => 0,
		) );

		add_settings_field(
			'newshare_default_required_bits',
			__( 'Default Access Tier', 'newshare-network' ),
			array( $this, 'render_tier_select' ),
			'newshare-network',
			'newshare_access'
		);

		$this->add_number_field(
			'newshare_free_article_count',
			__( 'Free Article Meter', 'newshare-network' ),
			'newshare_access',
			__( 'Number of gated articles anonymous users can read before being prompted to log in.', 'newshare-network' ),
			'1',
			'0'
		);

		// -----------------------------------------------------------------
		// Section 5: RSL Defaults
		// Default content license tag applied to all posts unless overridden.
		// RSL (Really Simple Licensing) is defined at rslstandard.org.
		// Common values: CC-BY-NC, CC-BY, All-Rights-Reserved.
		// -----------------------------------------------------------------
		add_settings_section(
			'newshare_rsl',
			__( 'RSL Defaults', 'newshare-network' ),
			array( $this, 'render_rsl_section' ),
			'newshare-network'
		);

		$this->add_text_field(
			'newshare_default_rsl_tag',
			__( 'Default RSL Tag', 'newshare-network' ),
			'newshare_rsl',
			__( 'Default content license tag (e.g., CC-BY-NC).', 'newshare-network' )
		);
	}

	// =========================================================================
	// Section Description Callbacks
	// =========================================================================

	/**
	 * Render the Network Identity section description.
	 */
	public function render_identity_section(): void {
		echo '<p>' . esc_html__( 'Configure your publisher identity within the Newshare Network.', 'newshare-network' ) . '</p>';
	}

	/**
	 * Render the ALS Endpoints section description.
	 */
	public function render_endpoints_section(): void {
		echo '<p>' . esc_html__( 'Configure the ALS (Account Ledger Service) endpoints. The OIDC flow goes through the ALS, not directly to Keycloak.', 'newshare-network' ) . '</p>';
	}

	/**
	 * Render the Content Pricing section description.
	 */
	public function render_pricing_section(): void {
		echo '<p>' . esc_html__( 'Set default wholesale pricing for your content. Individual posts can override these values.', 'newshare-network' ) . '</p>';
	}

	/**
	 * Render the Access Control section description.
	 */
	public function render_access_section(): void {
		echo '<p>' . esc_html__( 'Configure default access control settings. Individual posts can override the access tier.', 'newshare-network' ) . '</p>';
	}

	/**
	 * Render the RSL Defaults section description.
	 */
	public function render_rsl_section(): void {
		echo '<p>' . esc_html__( 'Configure default Resource Specification Language settings for content metadata.', 'newshare-network' ) . '</p>';
	}

	// =========================================================================
	// Custom Field Renderers
	// =========================================================================

	/**
	 * Render the default access tier select field.
	 *
	 * Displays a dropdown with predefined NetworkGroupId bitmask values.
	 * The selected value becomes the default required_bits for new posts
	 * that don't have a per-post override set.
	 */
	public function render_tier_select(): void {
		$value = get_option( 'newshare_default_required_bits', 0 );
		$tiers = array(
			0    => __( 'Free', 'newshare-network' ),
			2    => __( 'Registered', 'newshare-network' ),
			4    => __( 'Print Subscriber', 'newshare-network' ),
			8    => __( 'Digital Subscriber', 'newshare-network' ),
			4096 => __( 'Paid Subscriber', 'newshare-network' ),
			8192 => __( 'Trial', 'newshare-network' ),
		);

		echo '<select id="newshare_default_required_bits" name="newshare_default_required_bits">';
		foreach ( $tiers as $bit => $name ) {
			printf(
				'<option value="%s"%s>%s</option>',
				esc_attr( $bit ),
				selected( (int) $value, $bit, false ),
				esc_html( $name ) . ( $bit > 0 ? ' (' . esc_html( $bit ) . ')' : '' )
			);
		}
		echo '</select>';
		echo '<p class="description">' . esc_html__( 'Default access tier for new posts. 0 = free for everyone.', 'newshare-network' ) . '</p>';
	}

	// =========================================================================
	// Settings Page Rendering
	// =========================================================================

	/**
	 * Render the main settings page.
	 *
	 * Outputs the settings form (using the WordPress Settings API) and a
	 * "Test Connection" form that verifies the ALS is reachable.
	 */
	public function render_settings_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		// Handle the Test Connection action if the form was submitted.
		$test_result = null;
		if (
			isset( $_POST['newshare_test_connection'] ) &&
			check_admin_referer( 'newshare_test_connection', 'newshare_test_nonce' )
		) {
			$test_result = $this->test_connection();
		}

		?>
		<div class="wrap">
			<h1><?php esc_html_e( 'Newshare Network Settings', 'newshare-network' ); ?></h1>

			<?php settings_errors(); ?>

			<form method="post" action="options.php">
				<?php
				settings_fields( 'newshare-network' );
				do_settings_sections( 'newshare-network' );
				submit_button();
				?>
			</form>

			<hr />

			<h2><?php esc_html_e( 'Connection Test', 'newshare-network' ); ?></h2>
			<p><?php esc_html_e( 'Test the connection to the ALS by fetching the list of home bases.', 'newshare-network' ); ?></p>

			<form method="post" action="">
				<?php wp_nonce_field( 'newshare_test_connection', 'newshare_test_nonce' ); ?>
				<?php submit_button( __( 'Test Connection', 'newshare-network' ), 'secondary', 'newshare_test_connection', false ); ?>
			</form>

			<?php if ( null !== $test_result ) : ?>
				<div class="notice <?php echo $test_result['success'] ? 'notice-success' : 'notice-error'; ?> inline" style="margin-top: 15px;">
					<p><strong><?php echo $test_result['success'] ? esc_html__( 'Connection successful!', 'newshare-network' ) : esc_html__( 'Connection failed.', 'newshare-network' ); ?></strong></p>
					<?php if ( ! empty( $test_result['message'] ) ) : ?>
						<p><?php echo esc_html( $test_result['message'] ); ?></p>
					<?php endif; ?>
					<?php if ( ! empty( $test_result['data'] ) ) : ?>
						<pre style="background: #f0f0f0; padding: 10px; overflow-x: auto;"><?php echo esc_html( wp_json_encode( $test_result['data'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES ) ); ?></pre>
					<?php endif; ?>
				</div>
			<?php endif; ?>
		</div>
		<?php
	}

	// =========================================================================
	// Connection Test
	// =========================================================================

	/**
	 * Test the connection to the ALS by fetching the home bases list.
	 *
	 * Makes an authenticated GET request to the ALS /home-bases endpoint.
	 * A successful response confirms that:
	 *   - The ALS Auth URL is correct and reachable.
	 *   - The API key is valid.
	 *   - The ALS is operational.
	 *
	 * @return array{success: bool, message: string, data: mixed}
	 */
	private function test_connection(): array {
		$als_auth_endpoint = get_option( 'newshare_als_auth_endpoint' );
		$api_key           = get_option( 'newshare_als_api_key' );

		if ( empty( $als_auth_endpoint ) ) {
			return array(
				'success' => false,
				'message' => __( 'ALS Auth URL is not configured.', 'newshare-network' ),
				'data'    => null,
			);
		}

		$url = trailingslashit( $als_auth_endpoint ) . 'home-bases';

		$response = wp_remote_get(
			$url,
			array(
				'timeout' => 15,
				'headers' => array(
					'Accept'    => 'application/json',
					'X-API-Key' => $api_key,
				),
			)
		);

		if ( is_wp_error( $response ) ) {
			return array(
				'success' => false,
				'message' => $response->get_error_message(),
				'data'    => null,
			);
		}

		$status_code = wp_remote_retrieve_response_code( $response );
		$body        = wp_remote_retrieve_body( $response );
		$data        = json_decode( $body, true );

		if ( 200 !== $status_code ) {
			return array(
				'success' => false,
				'message' => sprintf(
					/* translators: %d: HTTP status code */
					__( 'ALS returned HTTP %d.', 'newshare-network' ),
					$status_code
				),
				'data'    => $data,
			);
		}

		return array(
			'success' => true,
			'message' => sprintf(
				/* translators: %d: number of home bases */
				__( 'Successfully connected. Found %d home base(s).', 'newshare-network' ),
				is_array( $data ) ? count( $data ) : 0
			),
			'data'    => $data,
		);
	}

	// =========================================================================
	// Field Registration Helpers
	// =========================================================================

	/**
	 * Helper: Register and add a text field to the settings page.
	 *
	 * Wraps the WordPress Settings API boilerplate for registering a text
	 * input field with a sanitization callback and description.
	 *
	 * @param string $option_name  The option name (stored in wp_options).
	 * @param string $label        The field label shown in the settings form.
	 * @param string $section      The settings section to attach this field to.
	 * @param string $description  Help text shown below the input field.
	 * @param string $type         HTML input type: 'text', 'url', or 'password'.
	 */
	private function add_text_field(
		string $option_name,
		string $label,
		string $section,
		string $description = '',
		string $type = 'text'
	): void {
		// Use URL-specific sanitization for URL fields.
		$sanitize = 'sanitize_text_field';
		if ( 'url' === $type ) {
			$sanitize = 'esc_url_raw';
		}

		register_setting( 'newshare-network', $option_name, array(
			'type'              => 'string',
			'sanitize_callback' => $sanitize,
			'default'           => '',
		) );

		add_settings_field(
			$option_name,
			$label,
			function () use ( $option_name, $description, $type ) {
				$value = get_option( $option_name, '' );
				printf(
					'<input type="%s" id="%s" name="%s" value="%s" class="regular-text" />',
					esc_attr( $type ),
					esc_attr( $option_name ),
					esc_attr( $option_name ),
					esc_attr( $value )
				);
				if ( ! empty( $description ) ) {
					printf( '<p class="description">%s</p>', esc_html( $description ) );
				}
			},
			'newshare-network',
			$section
		);
	}

	/**
	 * Helper: Register and add a number field to the settings page.
	 *
	 * Wraps the WordPress Settings API boilerplate for registering a numeric
	 * input field with step and min attributes.
	 *
	 * @param string $option_name  The option name (stored in wp_options).
	 * @param string $label        The field label shown in the settings form.
	 * @param string $section      The settings section to attach this field to.
	 * @param string $description  Help text shown below the input field.
	 * @param string $step         The HTML step attribute (e.g., '0.01' for cents).
	 * @param string $min          The HTML min attribute (e.g., '0' for non-negative).
	 */
	private function add_number_field(
		string $option_name,
		string $label,
		string $section,
		string $description = '',
		string $step = '1',
		string $min = '0'
	): void {
		register_setting( 'newshare-network', $option_name, array(
			'type'              => 'number',
			'sanitize_callback' => function ( $value ) {
				return is_numeric( $value ) ? $value : 0;
			},
			'default'           => 0,
		) );

		add_settings_field(
			$option_name,
			$label,
			function () use ( $option_name, $description, $step, $min ) {
				$value = get_option( $option_name, '' );
				printf(
					'<input type="number" id="%s" name="%s" value="%s" class="small-text" step="%s" min="%s" />',
					esc_attr( $option_name ),
					esc_attr( $option_name ),
					esc_attr( $value ),
					esc_attr( $step ),
					esc_attr( $min )
				);
				if ( ! empty( $description ) ) {
					printf( '<p class="description">%s</p>', esc_html( $description ) );
				}
			},
			'newshare-network',
			$section
		);
	}
}
