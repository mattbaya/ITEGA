<?php
/**
 * Updates from ITEGA, through WordPress's own update machinery.
 *
 * == Why ==
 *
 * This plugin is not in the WordPress.org directory, so by default a
 * publisher who installs it never hears about a new version again. That is
 * not a theoretical problem: Greylock Glass installed a build that was one
 * hour out of date, and the consequence was that their demonstration key was
 * never issued and two of our asset URLs sat in their page source. Neither
 * was visible to them, and the only remedy available was an email asking them
 * to download and reinstall by hand.
 *
 * A publisher hosting this as a favor should not have to do that every time
 * we fix something. So the plugin checks a manifest at ITEGA and reports any
 * newer version to WordPress, which then shows the ordinary "update
 * available" notice and the ordinary Update button. Nothing new to learn.
 *
 * == How ==
 *
 * WordPress asks every plugin to contribute to the update transient. We
 * answer with a package URL when the manifest names a version newer than the
 * one installed, and stay silent otherwise. `plugins_api` supplies the
 * details modal, so "View version details" is not an empty box.
 *
 * == Failure direction ==
 *
 * Every uncertain case resolves to "no update". An unreachable manifest,
 * malformed JSON, a missing version, a package URL that is not ours: all mean
 * WordPress hears nothing and the site carries on with what it has. An
 * updater that guesses is worse than one that is quiet, because it offers a
 * publisher a broken upgrade to a working site.
 *
 * @package Newshare_Network
 * @since   0.2.1
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Updater {

	/**
	 * Where the manifest lives.
	 *
	 * Same directory as the download and the documentation, so there is one
	 * place to publish to and one place to look.
	 */
	private const MANIFEST = 'https://dashboard.itega.org/plugin/update.json';

	/**
	 * Transient holding the last manifest we read.
	 */
	private const CACHE = 'newshare_update_manifest';

	/**
	 * How long to trust a cached manifest.
	 *
	 * Twelve hours: long enough that a site is not fetching this on every
	 * admin page load, short enough that a fix published in the morning is
	 * offered the same day.
	 */
	private const CACHE_TTL = 12 * HOUR_IN_SECONDS;

	/**
	 * Only ever offer a package served from here.
	 *
	 * The manifest is fetched over HTTPS, but this is the check that means a
	 * compromised or mistyped manifest cannot talk a publisher's site into
	 * installing code from somewhere else.
	 */
	private const PACKAGE_HOST = 'dashboard.itega.org';

	private string $basename;
	private string $slug;

	public function __construct( string $basename ) {
		$this->basename = $basename;                       // newshare-network/newshare-network.php
		$this->slug     = dirname( $basename );            // newshare-network
	}

	public function register(): void {
		add_filter( 'site_transient_update_plugins', array( $this, 'offer_update' ) );
		add_filter( 'plugins_api', array( $this, 'details' ), 10, 3 );
		// A publisher who has just been told to update should not wait up to
		// twelve hours for the notice to appear.
		add_action( 'upgrader_process_complete', array( $this, 'forget' ), 10, 0 );
		add_action( 'load-update-core.php', array( $this, 'forget' ) );
	}

	/**
	 * Drop the cached manifest.
	 */
	public function forget(): void {
		delete_transient( self::CACHE );
	}

	/**
	 * Read the manifest, cached.
	 *
	 * @return array<string,mixed>|null Null when it cannot be trusted.
	 */
	private function manifest(): ?array {
		$cached = get_transient( self::CACHE );
		if ( is_array( $cached ) ) {
			return $cached;
		}

		$response = wp_remote_get( self::MANIFEST, array( 'timeout' => 10 ) );
		if ( is_wp_error( $response ) || 200 !== (int) wp_remote_retrieve_response_code( $response ) ) {
			// Cache the failure briefly too, so a site whose outbound requests
			// are blocked does not retry on every single admin page view.
			set_transient( self::CACHE, array(), HOUR_IN_SECONDS );
			return null;
		}

		$data = json_decode( wp_remote_retrieve_body( $response ), true );
		if ( ! is_array( $data ) || empty( $data['version'] ) || empty( $data['download_url'] ) ) {
			set_transient( self::CACHE, array(), HOUR_IN_SECONDS );
			return null;
		}

		// Refuse a package from anywhere but ITEGA, whatever the manifest says.
		$host = wp_parse_url( (string) $data['download_url'], PHP_URL_HOST );
		if ( self::PACKAGE_HOST !== $host ) {
			set_transient( self::CACHE, array(), HOUR_IN_SECONDS );
			return null;
		}

		set_transient( self::CACHE, $data, self::CACHE_TTL );
		return $data;
	}

	/**
	 * Tell WordPress about a newer version, if there is one.
	 *
	 * @param mixed $transient The update transient WordPress is assembling.
	 * @return mixed
	 */
	public function offer_update( $transient ) {
		if ( ! is_object( $transient ) ) {
			return $transient;
		}

		$data = $this->manifest();
		if ( null === $data ) {
			return $transient;
		}

		$latest = (string) $data['version'];
		if ( ! version_compare( $latest, NEWSHARE_VERSION, '>' ) ) {
			// Up to date. Say so, so the Plugins screen does not imply
			// otherwise.
			$transient->no_update[ $this->basename ] = (object) array(
				'id'          => $this->basename,
				'slug'        => $this->slug,
				'plugin'      => $this->basename,
				'new_version' => NEWSHARE_VERSION,
				'url'         => (string) ( $data['homepage'] ?? '' ),
				'package'     => '',
			);
			return $transient;
		}

		$transient->response[ $this->basename ] = (object) array(
			'id'           => $this->basename,
			'slug'         => $this->slug,
			'plugin'       => $this->basename,
			'new_version'  => $latest,
			'url'          => (string) ( $data['homepage'] ?? '' ),
			'package'      => (string) $data['download_url'],
			'requires'     => (string) ( $data['requires'] ?? '' ),
			'requires_php' => (string) ( $data['requires_php'] ?? '' ),
			'tested'       => (string) ( $data['tested'] ?? '' ),
		);
		return $transient;
	}

	/**
	 * Fill in the "View version details" modal.
	 *
	 * @param mixed  $result The value being filtered.
	 * @param string $action The API action being performed.
	 * @param object $args   Arguments, including the requested slug.
	 * @return mixed
	 */
	public function details( $result, $action, $args ) {
		if ( 'plugin_information' !== $action
			|| empty( $args->slug ) || $args->slug !== $this->slug ) {
			return $result;
		}

		$data = $this->manifest();
		if ( null === $data ) {
			return $result;
		}

		return (object) array(
			'name'          => (string) ( $data['name'] ?? 'Newshare Network' ),
			'slug'          => $this->slug,
			'version'       => (string) $data['version'],
			'author'        => (string) ( $data['author'] ?? 'ITEGA' ),
			'homepage'      => (string) ( $data['homepage'] ?? '' ),
			'requires'      => (string) ( $data['requires'] ?? '' ),
			'requires_php'  => (string) ( $data['requires_php'] ?? '' ),
			'tested'        => (string) ( $data['tested'] ?? '' ),
			'last_updated'  => (string) ( $data['last_updated'] ?? '' ),
			'download_link' => (string) $data['download_url'],
			'sections'      => array_map( 'wp_kses_post', (array) ( $data['sections'] ?? array() ) ),
		);
	}
}
