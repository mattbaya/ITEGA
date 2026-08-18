<?php
/**
 * Newshare Access Control.
 *
 * This class controls content access based on the Newshare Network's bitmask
 * subscription tier model. It is the gatekeeper that decides whether a given
 * user can see a given piece of content.
 *
 * == Bitmask Access Control Model ==
 *
 * The Newshare Network uses a bitmask (NetworkGroupId) to encode subscription
 * tiers. Each tier is a power of 2, allowing users to hold multiple tiers
 * simultaneously via bitwise OR:
 *
 *   Bit Value | Tier Name
 *   ----------|------------------
 *        0    | Free (no bits set)
 *        2    | Registered (verified identity, no payment)
 *        4    | Print Subscriber
 *        8    | Digital Subscriber
 *     4096    | Paid Subscriber
 *     8192    | Trial
 *
 * Access check uses bitwise AND: a user can access content when ALL of the
 * content's required bits are present in the user's NetworkGroupId:
 *
 *   (user_group_id & required_bits) === required_bits
 *
 * Example: Content requires bits 4096 | 8 = 4104 (Paid + Digital).
 *          User has bits 4096 | 8 | 2 = 4106. Check: 4106 & 4104 = 4104. Access granted.
 *
 * == Anonymous Content Meter ==
 *
 * Non-network users (anonymous visitors) get a limited number of free article
 * views before being prompted to log in. This is tracked via a browser cookie
 * containing an array of viewed post IDs. The meter resets daily. The free
 * article limit is configurable in Settings > Newshare Network.
 *
 * == Access Gate ==
 *
 * When a user lacks access, their post content is replaced with:
 *   1. A truncated preview (first 80 words).
 *   2. An access gate UI (login prompt for anonymous users, or upgrade prompt
 *      for authenticated users with insufficient tier).
 *
 * @package Newshare_Network
 * @since   0.1.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Access {

	/**
	 * Tier bitmask to human-readable name mapping.
	 *
	 * These values correspond to the NetworkGroupId bitmask values defined
	 * in the Newshare Network protocol specification. Each value is a single
	 * bit position, allowing them to be combined with bitwise OR.
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
	 * Used to check if the current user has a network session and to read
	 * their NetworkGroupId for access control decisions.
	 *
	 * @var Newshare_Session
	 */
	private Newshare_Session $session;

	/**
	 * Pricing negotiator, used to get payment authorized before vending.
	 *
	 * @var Newshare_Pricing
	 */
	private Newshare_Pricing $pricing;

	/**
	 * Demonstration-audience gate.
	 *
	 * @var Newshare_Demo_Mode
	 */
	private Newshare_Demo_Mode $demo;

	/**
	 * Constructor.
	 *
	 * @param Newshare_Session $session Session manager (injected by the main plugin class).
	 * @param Newshare_Pricing $pricing Pricing negotiator (injected by the main plugin class).
	 */
	public function __construct(
		Newshare_Session $session,
		Newshare_Pricing $pricing,
		Newshare_Demo_Mode $demo
	) {
		$this->session = $session;
		$this->pricing = $pricing;
		$this->demo    = $demo;
	}

	// =========================================================================
	// Access Checking
	// =========================================================================

	/**
	 * Check whether the current user has access to a given post.
	 *
	 * Decision flow:
	 *   1. Look up the post's required_bits (per-post meta, or site default).
	 *   2. If required_bits is 0, the content is free -- everyone can access it.
	 *   3. If the reader is the publisher's own, serve it; see is_publisher_reader().
	 *   4. If the user is NOT a network user, fall through to the anonymous meter.
	 *   5. If the user IS a network user, check session validity and bitmask.
	 *
	 * @param int $post_id The post ID to check access for.
	 * @return bool True if the user has access, false otherwise.
	 */
	public function check_access( int $post_id ): bool {
		// Get the required access bits for this post (per-post override or site default).
		$required_bits = (int) get_post_meta( $post_id, 'newshare_required_bits', true );

		// Fall back to the site-wide default if not explicitly set on the post.
		if ( 0 === $required_bits && '' === get_post_meta( $post_id, 'newshare_required_bits', true ) ) {
			$required_bits = (int) get_option( 'newshare_default_required_bits', 0 );
		}

		// Free content (required_bits == 0) -- everyone can access, no checks needed.
		if ( 0 === $required_bits ) {
			return true;
		}

		// The publisher's own readers stay the publisher's own business.
		if ( $this->is_publisher_reader() ) {
			return true;
		}

		// If user is not logged in via the network, check the anonymous article meter.
		if ( ! $this->session->is_network_user() ) {
			return $this->check_anonymous_meter( $post_id );
		}

		// For network users, verify their session hasn't expired.
		if ( ! $this->session->is_session_valid() ) {
			return false;
		}

		// Bitmask check: user must have ALL required bits set in their NetworkGroupId.
		// Example: required=4104 (4096|8), user=4106 (4096|8|2) -> 4106 & 4104 = 4104 -> pass.
		$user_group_id = (int) get_user_meta( get_current_user_id(), 'newshare_network_group_id', true );
		return ( $user_group_id & $required_bits ) === $required_bits;
	}

	/**
	 * Whether the current reader is one of the publisher's own.
	 *
	 * A newspaper's existing relationships are not the network's to intermediate.
	 * Anyone signed in to this WordPress site who did not arrive through the
	 * network -- a subscriber, a monthly contributor, a member, staff -- reads
	 * everything on it and is never metered, gated, quoted or filed. The network
	 * is for visitors from elsewhere, and a publisher who installs the plugin
	 * must not find it standing between them and the people who already pay them.
	 *
	 * Network readers are always a separate account: find_or_create_user() never
	 * adopts a local one, deriving its username from the networkUserId instead.
	 *
	 * @return bool True if this is the publisher's own signed-in reader.
	 */
	private function is_publisher_reader(): bool {
		if ( ! is_user_logged_in() ) {
			return false;
		}

		if ( $this->session->is_network_user() ) {
			return false;
		}

		// A network account holds newshare_guest and nothing else. If its link
		// meta is ever lost -- a partial write, a restore, a manual edit --
		// is_network_user() goes false, and reading the meta alone would promote
		// that account to a member of the publisher's own audience with the run
		// of the site. Read the role too, and fail towards the gate.
		$user = wp_get_current_user();
		if ( array( NEWSHARE_ROLE ) === array_values( (array) $user->roles ) ) {
			return false;
		}

		return true;
	}

	// =========================================================================
	// Anonymous Article Meter
	// =========================================================================

	/**
	 * Check the anonymous article meter.
	 *
	 * Non-network users get a limited number of free articles per day
	 * (tracked via a cookie containing an array of viewed post IDs).
	 * This is a soft gate to encourage registration without completely
	 * blocking access.
	 *
	 * The meter behavior:
	 *   - Each unique post view counts as one article.
	 *   - Re-viewing an already-counted post does NOT decrement the meter.
	 *   - The cookie resets after 24 hours (DAY_IN_SECONDS).
	 *   - The limit is configurable via Settings > Newshare Network.
	 *
	 * Note: This uses a cookie, which is an exception to the "no cookies"
	 * rule in the OIDC flow. The meter cookie is purely client-side state
	 * for anonymous users and is NOT related to authentication.
	 *
	 * @param int $post_id The post ID being accessed.
	 * @return bool True if still within the free meter, false if exhausted.
	 */
	private function check_anonymous_meter( int $post_id ): bool {
		$limit = (int) get_option( 'newshare_free_article_count', 3 );
		if ( $limit <= 0 ) {
			return false;
		}

		// Read the current meter state from the cookie.
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

		// Check if the meter is exhausted (user has viewed the max free articles).
		if ( count( $viewed ) >= $limit ) {
			return false;
		}

		// Record this post view in the meter cookie.
		$viewed[]     = $post_id;
		$cookie_value = wp_json_encode( $viewed );
		if ( ! headers_sent() ) {
			setcookie( 'newshare_meter', $cookie_value, time() + DAY_IN_SECONDS, COOKIEPATH, COOKIE_DOMAIN, is_ssl(), true );
		}

		return true;
	}

	/**
	 * Whether a post carries a price this publisher is willing to sell at.
	 *
	 * A page_class of zero means the article is not for individual sale, so
	 * there is nothing to negotiate and the reader sees the ordinary tier gate.
	 *
	 * @param int $post_id Post to check.
	 * @return bool True if the post has a non-zero asking price.
	 */
	private function is_priced( int $post_id ): bool {
		$page_class = get_post_meta( $post_id, 'newshare_page_class', true );
		if ( '' === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}
		return (float) $page_class > 0;
	}

	/**
	 * Render the disclosure shown when a purchase has been authorized.
	 *
	 * The reader is told what they now owe their home base -- the retail price,
	 * which includes their home base's markup. This publisher is settled at the
	 * wholesale figure and never learns how the retail price was derived.
	 *
	 * @param array $quote Result from Newshare_Pricing::negotiate().
	 * @return string HTML notice.
	 */
	private function render_purchase_notice( array $quote ): string {
		return sprintf(
			'<div class="newshare-purchase-notice"><p>%s</p></div>',
			esc_html(
				sprintf(
					/* translators: %s: retail price charged by the reader's home base */
					__(
						'Purchased through your home base. Your account will be billed %s at settlement.',
						'newshare-network'
					),
					self::format_price( (float) $quote['retail_price'] )
				)
			)
		);
	}

	/**
	 * Render a price at the precision it actually carries.
	 *
	 * number_format( $x, 2 ) is the right default for money and the wrong one
	 * here: this network sells journalism in fractions of a cent, so 0.055
	 * becomes "$0.06" and the reader is told they owe more than they do. Pad to
	 * two places for ordinary amounts, then let genuinely finer figures keep
	 * their detail, trimming trailing zeros so $0.05 does not become $0.0500.
	 *
	 * @param float $amount Amount in dollars.
	 * @return string Formatted with a leading dollar sign.
	 */
	private static function format_price( float $amount ): string {
		$s = rtrim( rtrim( number_format( $amount, 4, '.', '' ), '0' ), '.' );
		if ( strpos( $s, '.' ) === false ) {
			$s .= '.00';
		} elseif ( strlen( substr( strrchr( $s, '.' ), 1 ) ) === 1 ) {
			$s .= '0';
		}
		return '$' . $s;
	}

	// =========================================================================
	// Content Filtering (Access Gate)
	// =========================================================================

	/**
	 * Filter post content to show access gate when the user lacks permissions.
	 *
	 * When a user does not have access to a post, this filter replaces the
	 * full content with:
	 *   1. A truncated preview (first 80 words of the article).
	 *   2. The access gate template (login prompt or upgrade message).
	 *
	 * Only applies to single post views in the main query loop -- not archives,
	 * feeds, or secondary queries.
	 *
	 * Hooked to: the_content
	 *
	 * @param string $content The post content.
	 * @return string Filtered content, possibly with an access gate replacing the body.
	 */
	public function filter_content( string $content ): string {
		// On a real publisher's site running in demo mode, a visitor who is not
		// part of the demonstration must never meet this plugin. Checked before
		// anything else so no pricing call, no meter cookie and no gate can
		// reach an ordinary reader.
		if ( $this->demo->should_suppress() ) {
			return $content;
		}

		// Only gate single post views, not archives or feeds.
		if ( ! is_singular( 'post' ) || ! in_the_loop() || ! is_main_query() ) {
			return $content;
		}

		$post_id = get_the_ID();
		if ( ! $post_id ) {
			return $content;
		}

		/**
		 * Allows a caller that has already paid to bypass the reader gate.
		 *
		 * Set by the AI agent handshake, which settles payment machine-to-machine
		 * before this filter runs. Without it a paid crawler would be handed the
		 * login prompt instead of the article it just bought, because the gate
		 * decides on a subscription tier a machine caller does not have.
		 *
		 * @param bool $bypass Whether to serve the content ungated.
		 */
		if ( apply_filters( 'newshare_bypass_access_gate', false ) ) {
			return $content;
		}

		// If the user's subscription tier grants access, the content is covered
		// by their existing relationship -- nothing to negotiate, serve it.
		if ( $this->check_access( $post_id ) ) {
			return $content;
		}

		// The tier does not cover this article, but a network reader may still
		// buy it if their home base authorizes payment. Ask before vending.
		if ( $this->session->is_network_user() && $this->is_priced( $post_id ) ) {
			$quote = $this->pricing->negotiate( $post_id );

			if ( 'accept' === $quote['decision'] ) {
				/**
				 * Fires when a purchase releases an article.
				 *
				 * The publisher has to file this itself. Settlement aggregates
				 * the publisher's own records, and the ordinary logging path only
				 * runs when check_access() is true -- that is, when the reader's
				 * tier already covered the article. A purchase is exactly the case
				 * where it did not, so without this the publisher never reports
				 * the transactions it is owed for, and settlement pays it nothing
				 * for them.
				 *
				 * @param int   $post_id The article being released.
				 * @param array $quote   Accepted quote, carrying agreed_price.
				 */
				do_action( 'newshare_content_purchased', $post_id, $quote );

				// Payment authorized. Show the reader what they have committed
				// to pay their home base, then release the article.
				return $this->render_purchase_notice( $quote ) . $content;
			}

			// The home base was reached and refused, or could not be reached.
			// Either way we withhold the article and tell the reader to take it
			// up with their home base, which is the party that decides.
			ob_start();
			$decline_reason = $quote['reason'];
			$home_base_url  = $quote['home_base_url'] ?? '';
			include NEWSHARE_PLUGIN_DIR . 'templates/payment-declined.php';
			$gate = ob_get_clean();

			return wp_trim_words( wp_strip_all_tags( $content ), 80, '&hellip;' ) . $gate;
		}

		// -- User lacks access: build and display the access gate. --

		// Look up the required bits for this post (needed for the tier name display).
		$required_bits = (int) get_post_meta( $post_id, 'newshare_required_bits', true );
		if ( 0 === $required_bits && '' === get_post_meta( $post_id, 'newshare_required_bits', true ) ) {
			$required_bits = (int) get_option( 'newshare_default_required_bits', 0 );
		}

		// Generate a truncated preview of the article (first 80 words, stripped of HTML).
		$preview = wp_trim_words( wp_strip_all_tags( $content ), 80, '&hellip;' );

		// Capture the current page URL so the access gate can pass it through the OIDC flow.
		// This ensures the user returns to this article after logging in.
		$current_url = get_permalink( $post_id );

		// What this publisher is asking for this article.
		//
		// Shown to the reader, because "you must sign in to read this" without
		// a number invites them to imagine a subscription. Jason Velazquez at
		// Greylock Glass asked for reassurance that articles cost very little;
		// the honest version of that is not a claim about what articles
		// typically cost, it is this article's actual price.
		$page_class = get_post_meta( $post_id, 'newshare_page_class', true );
		if ( '' === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}
		$page_class = (float) $page_class;

		// Render the access gate template.
		ob_start();
		$tier_name       = $this->get_tier_name( $required_bits );
		$is_network_user = $this->session->is_network_user();
		include NEWSHARE_PLUGIN_DIR . 'templates/access-gate.php';
		$gate_html = ob_get_clean();

		return '<div class="newshare-preview">' . wpautop( $preview ) . '</div>' . $gate_html;
	}

	// =========================================================================
	// Tier Name Resolution
	// =========================================================================

	/**
	 * Map a bitmask value to a human-readable tier name.
	 *
	 * For single-bit values, returns the exact tier name (e.g., "Paid Subscriber").
	 * For composite bitmasks (multiple bits set), returns a combined name
	 * (e.g., "Digital Subscriber + Paid Subscriber").
	 *
	 * @param int $bits The bitmask value.
	 * @return string Human-readable tier name.
	 */
	public function get_tier_name( int $bits ): string {
		// Exact match for single-tier bitmasks.
		if ( isset( self::TIER_NAMES[ $bits ] ) ) {
			return self::TIER_NAMES[ $bits ];
		}

		// Build a composite name from individual bits for multi-tier requirements.
		$names = array();
		foreach ( self::TIER_NAMES as $bit => $name ) {
			if ( 0 === $bit ) {
				continue; // Skip "Free" -- it's the absence of bits, not a tier.
			}
			if ( ( $bits & $bit ) === $bit ) {
				$names[] = $name;
			}
		}

		return ! empty( $names ) ? implode( ' + ', $names ) : __( 'Premium', 'newshare-network' );
	}

	// =========================================================================
	// Post Editor Meta Box
	// =========================================================================

	/**
	 * Add the "Newshare Access Control" meta box to the post editor.
	 *
	 * This meta box allows editors to set per-post overrides for:
	 *   - Required access tier (NetworkGroupId bitmask)
	 *   - Page class (wholesale price)
	 *   - RSL tag (content license)
	 *
	 * If left blank, site-wide defaults from the plugin settings are used.
	 *
	 * Hooked to: add_meta_boxes
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
	 * Render the access control meta box in the post editor.
	 *
	 * Displays three fields:
	 *   - Required Access Tier (dropdown of known tier bitmasks)
	 *   - Page Class (numeric input for wholesale price in dollars)
	 *   - RSL Tag (text input for the content license string)
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

	// =========================================================================
	// Meta Box Save
	// =========================================================================

	/**
	 * Save the access control meta box data when a post is saved.
	 *
	 * Validates the nonce, checks permissions, and saves the per-post
	 * overrides for required_bits, page_class, and rsl_tag. If a field
	 * is left blank, the post meta is deleted so the site default is used.
	 *
	 * Hooked to: save_post
	 *
	 * @param int $post_id The post ID being saved.
	 */
	public function save_meta_box( int $post_id ): void {
		// Verify nonce to ensure the save request came from our meta box form.
		if (
			! isset( $_POST['newshare_access_nonce'] ) ||
			! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['newshare_access_nonce'] ) ), 'newshare_access_meta' )
		) {
			return;
		}

		// Don't save during autosave -- only on intentional saves.
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}

		// Verify the user has permission to edit this post.
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}

		// Save required access tier bits (or delete meta if blank to use site default).
		if ( isset( $_POST['newshare_required_bits'] ) ) {
			$value = sanitize_text_field( wp_unslash( $_POST['newshare_required_bits'] ) );
			if ( '' === $value ) {
				delete_post_meta( $post_id, 'newshare_required_bits' );
			} else {
				update_post_meta( $post_id, 'newshare_required_bits', absint( $value ) );
			}
		}

		// Save page class / wholesale price (or delete meta if blank).
		if ( isset( $_POST['newshare_page_class'] ) ) {
			$value = sanitize_text_field( wp_unslash( $_POST['newshare_page_class'] ) );
			if ( '' === $value ) {
				delete_post_meta( $post_id, 'newshare_page_class' );
			} else {
				update_post_meta( $post_id, 'newshare_page_class', floatval( $value ) );
			}
		}

		// Save RSL tag / content license (or delete meta if blank).
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
