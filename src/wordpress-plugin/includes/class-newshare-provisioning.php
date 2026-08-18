<?php
/**
 * Self-provisioning: ask ITEGA for this site's settings.
 *
 * == Why the plugin ships with no credentials ==
 *
 * The distributable is a public download. Anything baked into it is public,
 * so a Publishing Member ID and an exchange API key cannot travel inside it.
 * The alternative used to be a settings form and an email containing a key,
 * which puts a shared secret through a mail client and then asks a publisher
 * to paste it correctly.
 *
 * Instead ITEGA registers a publisher's domains when it certifies them --
 * that is where the paperwork, the banking details and the governance sit --
 * and the plugin asks for its own credentials on activation. The publisher
 * installs, activates, and is done.
 *
 * == What the exchange will and will not answer ==
 *
 * A domain must already be registered, and each registration can be claimed
 * exactly once. An unregistered domain is refused and told to contact ITEGA.
 * A domain already claimed is refused too, which is the interesting case: it
 * means either this site is being reinstalled, in which case ITEGA can
 * release it, or somebody else claimed it first, in which case the publisher
 * finds out now rather than never.
 *
 * @package Newshare_Network
 * @since   0.2.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Provisioning {

	/**
	 * Option holding the last provisioning outcome, for the settings page.
	 */
	private const STATUS = 'newshare_provisioning_status';

	/**
	 * Option holding the challenge nonce currently being served.
	 */
	private const NONCE = 'newshare_provisioning_nonce';

	/** Stops a site that cannot certify from asking on every page load. */
	private const HEALING = 'newshare_provisioning_attempt';

	/** How long to wait before trying again. */
	private const HEAL_INTERVAL = HOUR_IN_SECONDS;

	/** When the exchange last confirmed this site's key. */
	private const VERIFIED = 'newshare_credentials_verified';

	/** When the key was first refused. One refusal is a race; two is a revocation. */
	private const DOUBT = 'newshare_credentials_doubt';

	/** How far apart two refusals must be before the key is believed dead. */
	private const DOUBT_INTERVAL = HOUR_IN_SECONDS;

	/**
	 * Path this site serves the challenge from.
	 *
	 * Under /.well-known/ rather than a plugin route, so it survives the site
	 * moving to another CMS and can be satisfied with a static file if
	 * WordPress cannot serve it.
	 */
	public const CHALLENGE_PATH = '/.well-known/newshare-challenge';

	/**
	 * Serve the challenge, if one is outstanding.
	 *
	 * Hooked on ``parse_request`` so it answers before WordPress resolves the
	 * URL to a 404. Prints the nonce as plain text and nothing else: the
	 * exchange compares the whole body, so a theme wrapper or a stray newline
	 * from a template would fail the check.
	 */
	public static function serve_challenge(): void {
		$path = wp_parse_url( $_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH );
		if ( self::CHALLENGE_PATH !== $path ) {
			return;
		}

		$nonce = (string) get_option( self::NONCE, '' );
		if ( '' === $nonce ) {
			return;   // Nothing outstanding; let WordPress 404 as usual.
		}

		header( 'Content-Type: text/plain; charset=utf-8' );
		header( 'Cache-Control: no-store' );
		echo esc_html( $nonce );
		exit;
	}

	/**
	 * The domain this site reports as its own.
	 *
	 * Taken from home_url() rather than any request header: a header is
	 * whatever the caller sent, and this must be what WordPress believes it
	 * is. The exchange normalises away www., scheme, port and path.
	 *
	 * @return string
	 */
	public static function domain(): string {
		$host = wp_parse_url( home_url(), PHP_URL_HOST );
		return is_string( $host ) ? $host : '';
	}

	/**
	 * Whether this site already has what it needs.
	 *
	 * @return bool
	 */
	public static function is_configured(): bool {
		return '' !== trim( (string) get_option( 'newshare_pub_mbr_id', '' ) )
			&& '' !== trim( (string) get_option( 'newshare_als_api_key', '' ) );
	}

	/**
	 * Ask ITEGA for this site's credentials and store them.
	 *
	 * Safe to call more than once: it returns early if the site is already
	 * configured, so a reactivation does not burn the site's one claim.
	 *
	 * @param bool $force Ask even if already configured.
	 * @return array{ok:bool,message:string}
	 */
	/**
	 * Credentials this site once had and no longer does are worth re-fetching.
	 *
	 * They live in options rather than in the plugin directory, which is what
	 * lets a WordPress update replace the plugin without de-provisioning the
	 * site. But options are lost in other ways -- a database restore, a
	 * migration, a staging clone, someone deleting a row -- and nothing used to
	 * bring them back. Provisioning is scheduled once, at activation, and an
	 * update does not re-activate.
	 *
	 * The consequence is the worst shape a fault can have here. The site keeps
	 * working to look at: the meter counts, the gate closes on the fourth
	 * article, readers are charged by their home bases. What it cannot do is
	 * file events, because that needs the key -- so settlement pays the
	 * publisher nothing, and no error appears anywhere a person would look.
	 * Verified on a live site by deleting both options: three free reads, a gate
	 * on the fourth, and nothing filed. #50.
	 *
	 * Scheduled rather than run inline: the exchange has to fetch a nonce back
	 * from this site over HTTPS, which is seconds, and no reader should wait for
	 * it. Rate-limited so a site that genuinely cannot certify -- an unreachable
	 * domain, a withdrawn registration -- asks once an hour instead of on every
	 * page load.
	 */
	public static function heal(): void {
		if ( self::is_configured() ) {
			return;
		}
		if ( get_transient( self::HEALING ) ) {
			return;
		}
		set_transient( self::HEALING, time(), self::HEAL_INTERVAL );
		if ( ! wp_next_scheduled( 'newshare_provision_event' ) ) {
			wp_schedule_single_event( time(), 'newshare_provision_event' );
		}
	}

	/**
	 * Ask the exchange whether this site's key still works.
	 *
	 * Event filing is fire-and-forget -- blocking a reader's page load on a log
	 * write would be indefensible -- so the plugin never sees a rejection. This
	 * is the one place it can wait for an answer, and it runs on a schedule
	 * rather than in front of anybody.
	 *
	 * A 403 means the exchange does not hold this key: revoked, rotated, or
	 * restored from a backup taken before it was issued. Clearing it turns the
	 * next heal() into a fresh certification, which the site can perform on its
	 * own because it still controls its domain.
	 *
	 * Anything else -- a timeout, a 500, a DNS failure -- is left alone. A
	 * working key must not be thrown away because the exchange was briefly down;
	 * that would turn a five-minute outage into every publisher re-certifying at
	 * once.
	 */
	public static function verify(): void {
		$key = trim( (string) get_option( 'newshare_als_api_key', '' ) );
		if ( '' === $key ) {
			self::heal();
			return;
		}

		$endpoint = untrailingslashit(
			(string) get_option( 'newshare_als_logging_endpoint', 'https://als.itega.org' )
		) . '/log/whoami';

		$response = wp_remote_get(
			$endpoint,
			array(
				'timeout' => 10,
				'headers' => array( 'X-API-Key' => $key ),
			)
		);

		if ( is_wp_error( $response ) ) {
			return;
		}

		$code = (int) wp_remote_retrieve_response_code( $response );
		if ( 403 !== $code ) {
			if ( 200 === $code ) {
				update_option( self::VERIFIED, time() );
				delete_option( self::DOUBT );
			}
			return;
		}

		// 403 also covers "this key may not file for that member ID", but that
		// answer cannot arrive here: this request carries no member ID. So a 403
		// means the exchange does not hold this key.
		//
		// It is still not enough to act on. A key issued moments ago can be
		// rejected briefly, because the discovery service writes the key store
		// and the logging service reads it, and those are not the same instant.
		// The first version of this deleted a perfectly good key on that race,
		// then healed, then deleted the replacement -- a site could sit in that
		// loop indefinitely, re-certifying every hour and never able to file.
		// Caught on wesmc.org, where provisioning reported success and the key
		// was gone immediately afterwards.
		//
		// So a single refusal only raises a doubt. Two, an hour or more apart,
		// are a revocation. A genuinely withdrawn key still recovers the same
		// day; a race resolves itself with nothing thrown away.
		$doubt = (int) get_option( self::DOUBT, 0 );
		if ( 0 === $doubt ) {
			update_option( self::DOUBT, time() );
			return;
		}
		if ( time() - $doubt < self::DOUBT_INTERVAL ) {
			return;
		}

		delete_option( self::DOUBT );
		delete_option( 'newshare_als_api_key' );
		delete_transient( self::HEALING );
		self::heal();
	}

	public static function provision( bool $force = false ): array {
		if ( self::is_configured() && ! $force ) {
			return self::done( true, __( 'Already configured.', 'newshare-network' ) );
		}

		$domain = self::domain();
		if ( '' === $domain ) {
			return self::done( false, __( 'Could not determine this site\'s domain.', 'newshare-network' ) );
		}

		// Publish a fresh nonce before asking. The exchange will fetch it back
		// from this site over HTTPS, which is what proves we are who we say:
		// anyone can claim a domain, but only this site can answer for it.
		$nonce = wp_generate_password( 43, false, false );
		update_option( self::NONCE, $nonce );

		$endpoint = untrailingslashit(
			(string) get_option( 'newshare_discovery_endpoint', 'https://network.itega.org' )
		) . '/provision';

		$response = wp_remote_post(
			$endpoint,
			array(
				'timeout' => 30,   // The exchange fetches this site mid-request.
				'headers' => array( 'Content-Type' => 'application/json' ),
				'body'    => wp_json_encode(
					array(
						'domain' => $domain,
						'nonce'  => $nonce,
					)
				),
			)
		);

		if ( is_wp_error( $response ) ) {
			// A network failure is not a refusal. Leave the site unconfigured
			// and let the operator retry from the settings page rather than
			// recording something that looks like a decision.
			return self::done(
				false,
				sprintf(
					/* translators: %s: error message */
					__( 'Could not reach ITEGA: %s', 'newshare-network' ),
					$response->get_error_message()
				)
			);
		}

		$code = (int) wp_remote_retrieve_response_code( $response );
		$body = json_decode( wp_remote_retrieve_body( $response ), true );

		if ( 200 !== $code ) {
			$detail = is_array( $body ) && isset( $body['detail'] )
				? (string) $body['detail']
				: sprintf( /* translators: %d: HTTP status */ __( 'HTTP %d', 'newshare-network' ), $code );
			return self::done( false, $detail );
		}

		if ( ! is_array( $body ) || empty( $body['pub_mbr_id'] ) || empty( $body['api_key'] ) ) {
			return self::done( false, __( 'ITEGA returned an incomplete response.', 'newshare-network' ) );
		}

		// update_option, not add_option: this is the authoritative answer and
		// it must replace whatever was there, including a previous attempt.
		update_option( 'newshare_pub_mbr_id', sanitize_text_field( $body['pub_mbr_id'] ) );
		update_option( 'newshare_als_api_key', sanitize_text_field( $body['api_key'] ) );

		// The demonstration key, issued rather than invented. Demo mode stays
		// on: this is what lets the publisher (and only whoever they give it
		// to) see the plugin working, while ordinary readers still cannot.
		// Set with add_option semantics -- a publisher who has chosen their
		// own key keeps it.
		if ( ! empty( $body['demo_key'] ) && '' === trim( (string) get_option( 'newshare_demo_key', '' ) ) ) {
			update_option( 'newshare_demo_key', sanitize_text_field( $body['demo_key'] ) );
		}

		foreach ( array(
			'als_auth_endpoint'    => 'newshare_als_auth_endpoint',
			'als_logging_endpoint' => 'newshare_als_logging_endpoint',
			'discovery_endpoint'   => 'newshare_discovery_endpoint',
			'als_public_key_url'   => 'newshare_als_public_key_url',
		) as $from => $option ) {
			if ( ! empty( $body[ $from ] ) ) {
				update_option( $option, esc_url_raw( $body[ $from ] ) );
			}
		}

		$name = isset( $body['name'] ) ? (string) $body['name'] : $domain;
		return self::done(
			true,
			sprintf(
				/* translators: 1: publisher name, 2: member ID */
				__( 'Provisioned as %1$s (%2$s).', 'newshare-network' ),
				$name,
				(string) $body['pub_mbr_id']
			)
		);
	}

	/**
	 * Record and return the outcome.
	 *
	 * @param bool   $ok      Whether provisioning succeeded.
	 * @param string $message Human-readable detail.
	 * @return array{ok:bool,message:string}
	 */
	private static function done( bool $ok, string $message ): array {
		// The nonce is single-use. Leaving it served would let anyone who saw
		// it replay the proof from elsewhere for as long as it stayed up.
		delete_option( self::NONCE );

		update_option(
			self::STATUS,
			array(
				'ok'      => $ok,
				'message' => $message,
				'at'      => time(),
			)
		);
		return array(
			'ok'      => $ok,
			'message' => $message,
		);
	}

	/**
	 * The last outcome, for display.
	 *
	 * @return array{ok:bool,message:string,at:int}|null
	 */
	public static function status(): ?array {
		$status = get_option( self::STATUS );
		return is_array( $status ) ? $status : null;
	}
}
