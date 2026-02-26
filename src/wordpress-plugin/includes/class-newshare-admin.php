<?php
/**
 * Newshare Admin Settings Page.
 *
 * Provides the Settings > Newshare Network admin page where publishers
 * configure their network member ID, ALS endpoints, pricing defaults,
 * and access tier settings.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Admin {

	/**
	 * Add the settings page under the Settings menu.
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

	/**
	 * Register all settings, sections, and fields using the Settings API.
	 */
	public function register_settings(): void {
		// --- Network Identity Section ---
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

		// --- ALS Endpoints Section ---
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

		// --- Content Pricing Section ---
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

		// --- Access Control Section ---
		add_settings_section(
			'newshare_access',
			__( 'Access Control', 'newshare-network' ),
			array( $this, 'render_access_section' ),
			'newshare-network'
		);

		// Default required bits — use a select field.
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

		// --- RSL Defaults Section ---
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

	/**
	 * Section description callbacks.
	 */
	public function render_identity_section(): void {
		echo '<p>' . esc_html__( 'Configure your publisher identity within the Newshare Network.', 'newshare-network' ) . '</p>';
	}

	public function render_endpoints_section(): void {
		echo '<p>' . esc_html__( 'Configure the ALS (Account Ledger Service) endpoints. The OIDC flow goes through the ALS, not directly to Keycloak.', 'newshare-network' ) . '</p>';
	}

	public function render_pricing_section(): void {
		echo '<p>' . esc_html__( 'Set default wholesale pricing for your content. Individual posts can override these values.', 'newshare-network' ) . '</p>';
	}

	public function render_access_section(): void {
		echo '<p>' . esc_html__( 'Configure default access control settings. Individual posts can override the access tier.', 'newshare-network' ) . '</p>';
	}

	public function render_rsl_section(): void {
		echo '<p>' . esc_html__( 'Configure default Resource Specification Language settings for content metadata.', 'newshare-network' ) . '</p>';
	}

	/**
	 * Render the default access tier select field.
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

	/**
	 * Render the settings page.
	 */
	public function render_settings_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		// Handle the Test Connection action.
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

	/**
	 * Test the connection to the ALS by fetching home bases.
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

	/**
	 * Helper: Register and add a text field.
	 *
	 * @param string $option_name  The option name.
	 * @param string $label        The field label.
	 * @param string $section      The settings section.
	 * @param string $description  The field description.
	 * @param string $type         Input type: text, url, or password.
	 */
	private function add_text_field(
		string $option_name,
		string $label,
		string $section,
		string $description = '',
		string $type = 'text'
	): void {
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
	 * Helper: Register and add a number field.
	 *
	 * @param string $option_name  The option name.
	 * @param string $label        The field label.
	 * @param string $section      The settings section.
	 * @param string $description  The field description.
	 * @param string $step         The step attribute.
	 * @param string $min          The min attribute.
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
