<?php
/**
 * Newshare Access Control.
 *
 * Controls content access based on subscription tiers using bitmask logic.
 * NetworkGroupId is a bitmask: 4096=Paid, 4=Print, 8=Digital, etc.
 * Access is checked via bitwise AND: user must have all required bits set.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Access {

	/**
	 * Tier bitmask to human-readable name mapping.
	 *
	 * @var array<int, string>
	 */
	private const TIER_NAMES = array(
		0    => 'Free',
		2    => 'Registered',
		4    => 'Print Subscriber',
		8    => 'Digital Subscriber',
		4096 => 'Paid Subscriber',
		8192 => 'Trial',
	);

	/**
	 * Session manager instance.
	 *
	 * @var Newshare_Session
	 */
	private Newshare_Session $session;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session $session Session manager.
	 */
	public function __construct( Newshare_Session $session ) {
		$this->session = $session;
	}

	/**
	 * Check whether the current user has access to a given post.
	 *
	 * @param int $post_id The post ID to check access for.
	 * @return bool True if the user has access, false otherwise.
	 */
	public function check_access( int $post_id ): bool {
		// Get the required access bits for this post.
		$required_bits = (int) get_post_meta( $post_id, 'newshare_required_bits', true );

		// Fall back to the site-wide default if not set on the post.
		if ( 0 === $required_bits && '' === get_post_meta( $post_id, 'newshare_required_bits', true ) ) {
			$required_bits = (int) get_option( 'newshare_default_required_bits', 0 );
		}

		// Free content — everyone can access.
		if ( 0 === $required_bits ) {
			return true;
		}

		// If user is not logged in via the network, check anonymous meter.
		if ( ! $this->session->is_network_user() ) {
			return $this->check_anonymous_meter( $post_id );
		}

		// Check session validity.
		if ( ! $this->session->is_session_valid() ) {
			return false;
		}

		// Bitmask check: user must have ALL required bits set.
		$user_group_id = (int) get_user_meta( get_current_user_id(), 'newshare_network_group_id', true );
		return ( $user_group_id & $required_bits ) === $required_bits;
	}

	/**
	 * Check the anonymous article meter.
	 *
	 * Non-network users get a limited number of free articles per session
	 * (tracked via a cookie).
	 *
	 * @param int $post_id The post ID being accessed.
	 * @return bool True if still within the free meter, false if exhausted.
	 */
	private function check_anonymous_meter( int $post_id ): bool {
		$limit = (int) get_option( 'newshare_free_article_count', 3 );
		if ( $limit <= 0 ) {
			return false;
		}

		$viewed = array();
		if ( isset( $_COOKIE['newshare_meter'] ) ) {
			$decoded = json_decode( sanitize_text_field( wp_unslash( $_COOKIE['newshare_meter'] ) ), true );
			if ( is_array( $decoded ) ) {
				$viewed = array_map( 'absint', $decoded );
			}
		}

		// If this post has already been viewed, don't count it again.
		if ( in_array( $post_id, $viewed, true ) ) {
			return true;
		}

		// Check if the meter is exhausted.
		if ( count( $viewed ) >= $limit ) {
			return false;
		}

		// Record this post view in the meter cookie.
		$viewed[] = $post_id;
		$cookie_value = wp_json_encode( $viewed );
		if ( ! headers_sent() ) {
			setcookie( 'newshare_meter', $cookie_value, time() + DAY_IN_SECONDS, COOKIEPATH, COOKIE_DOMAIN, is_ssl(), true );
		}

		return true;
	}

	/**
	 * Filter post content to show access gate when the user lacks permissions.
	 *
	 * Hooked to `the_content`.
	 *
	 * @param string $content The post content.
	 * @return string Filtered content, possibly with an access gate.
	 */
	public function filter_content( string $content ): string {
		// Only gate single post views, not archives or feeds.
		if ( ! is_singular( 'post' ) || ! in_the_loop() || ! is_main_query() ) {
			return $content;
		}

		$post_id = get_the_ID();
		if ( ! $post_id ) {
			return $content;
		}

		// If the user has access, return content unchanged.
		if ( $this->check_access( $post_id ) ) {
			return $content;
		}

		// Build the access gate.
		$required_bits = (int) get_post_meta( $post_id, 'newshare_required_bits', true );
		if ( 0 === $required_bits && '' === get_post_meta( $post_id, 'newshare_required_bits', true ) ) {
			$required_bits = (int) get_option( 'newshare_default_required_bits', 0 );
		}

		// Generate a truncated preview.
		$preview = wp_trim_words( wp_strip_all_tags( $content ), 80, '&hellip;' );

		ob_start();
		$tier_name      = $this->get_tier_name( $required_bits );
		$is_network_user = $this->session->is_network_user();
		include NEWSHARE_PLUGIN_DIR . 'templates/access-gate.php';
		$gate_html = ob_get_clean();

		return '<div class="newshare-preview">' . wpautop( $preview ) . '</div>' . $gate_html;
	}

	/**
	 * Map a bitmask value to a human-readable tier name.
	 *
	 * @param int $bits The bitmask value.
	 * @return string Human-readable tier name.
	 */
	public function get_tier_name( int $bits ): string {
		if ( isset( self::TIER_NAMES[ $bits ] ) ) {
			return self::TIER_NAMES[ $bits ];
		}

		// Build a composite name from individual bits.
		$names = array();
		foreach ( self::TIER_NAMES as $bit => $name ) {
			if ( 0 === $bit ) {
				continue;
			}
			if ( ( $bits & $bit ) === $bit ) {
				$names[] = $name;
			}
		}

		return ! empty( $names ) ? implode( ' + ', $names ) : __( 'Premium', 'newshare-network' );
	}

	/**
	 * Add the "Newshare Access Control" meta box to the post editor.
	 */
	public function add_meta_box(): void {
		add_meta_box(
			'newshare_access_control',
			__( 'Newshare Access Control', 'newshare-network' ),
			array( $this, 'render_meta_box' ),
			'post',
			'side',
			'default'
		);
	}

	/**
	 * Render the access control meta box.
	 *
	 * @param WP_Post $post The current post object.
	 */
	public function render_meta_box( WP_Post $post ): void {
		wp_nonce_field( 'newshare_access_meta', 'newshare_access_nonce' );

		$required_bits = get_post_meta( $post->ID, 'newshare_required_bits', true );
		$page_class    = get_post_meta( $post->ID, 'newshare_page_class', true );
		$rsl_tag       = get_post_meta( $post->ID, 'newshare_rsl_tag', true );

		?>
		<p>
			<label for="newshare_required_bits">
				<strong><?php esc_html_e( 'Required Access Tier', 'newshare-network' ); ?></strong>
			</label>
			<select id="newshare_required_bits" name="newshare_required_bits" class="widefat">
				<option value="" <?php selected( $required_bits, '' ); ?>>
					<?php esc_html_e( '-- Use site default --', 'newshare-network' ); ?>
				</option>
				<?php foreach ( self::TIER_NAMES as $bit => $name ) : ?>
					<option value="<?php echo esc_attr( $bit ); ?>" <?php selected( (string) $required_bits, (string) $bit ); ?>>
						<?php echo esc_html( $name ); ?>
						<?php if ( $bit > 0 ) : ?>
							(<?php echo esc_html( $bit ); ?>)
						<?php endif; ?>
					</option>
				<?php endforeach; ?>
			</select>
		</p>
		<p>
			<label for="newshare_page_class">
				<strong><?php esc_html_e( 'Page Class (Wholesale Price)', 'newshare-network' ); ?></strong>
			</label>
			<input
				type="number"
				id="newshare_page_class"
				name="newshare_page_class"
				value="<?php echo esc_attr( $page_class ); ?>"
				class="widefat"
				step="0.01"
				min="0"
				placeholder="<?php echo esc_attr( get_option( 'newshare_default_page_class', '0.05' ) ); ?>"
			/>
			<span class="description">
				<?php esc_html_e( 'Leave blank to use site default.', 'newshare-network' ); ?>
			</span>
		</p>
		<p>
			<label for="newshare_rsl_tag">
				<strong><?php esc_html_e( 'RSL Tag', 'newshare-network' ); ?></strong>
			</label>
			<input
				type="text"
				id="newshare_rsl_tag"
				name="newshare_rsl_tag"
				value="<?php echo esc_attr( $rsl_tag ); ?>"
				class="widefat"
				placeholder="<?php echo esc_attr( get_option( 'newshare_default_rsl_tag', 'CC-BY-NC' ) ); ?>"
			/>
			<span class="description">
				<?php esc_html_e( 'Leave blank to use site default.', 'newshare-network' ); ?>
			</span>
		</p>
		<?php
	}

	/**
	 * Save the access control meta box data.
	 *
	 * @param int $post_id The post ID being saved.
	 */
	public function save_meta_box( int $post_id ): void {
		// Verify nonce.
		if (
			! isset( $_POST['newshare_access_nonce'] ) ||
			! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['newshare_access_nonce'] ) ), 'newshare_access_meta' )
		) {
			return;
		}

		// Check autosave.
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}

		// Check permissions.
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}

		// Save required bits.
		if ( isset( $_POST['newshare_required_bits'] ) ) {
			$value = sanitize_text_field( wp_unslash( $_POST['newshare_required_bits'] ) );
			if ( '' === $value ) {
				delete_post_meta( $post_id, 'newshare_required_bits' );
			} else {
				update_post_meta( $post_id, 'newshare_required_bits', absint( $value ) );
			}
		}

		// Save page class.
		if ( isset( $_POST['newshare_page_class'] ) ) {
			$value = sanitize_text_field( wp_unslash( $_POST['newshare_page_class'] ) );
			if ( '' === $value ) {
				delete_post_meta( $post_id, 'newshare_page_class' );
			} else {
				update_post_meta( $post_id, 'newshare_page_class', floatval( $value ) );
			}
		}

		// Save RSL tag.
		if ( isset( $_POST['newshare_rsl_tag'] ) ) {
			$value = sanitize_text_field( wp_unslash( $_POST['newshare_rsl_tag'] ) );
			if ( '' === $value ) {
				delete_post_meta( $post_id, 'newshare_rsl_tag' );
			} else {
				update_post_meta( $post_id, 'newshare_rsl_tag', $value );
			}
		}
	}
}
