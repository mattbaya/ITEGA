<?php
/**
 * What this publication is owed, on a page rather than in an API.
 *
 * A publisher could always get these numbers -- GET /log/report/publisher/{id}
 * has returned them since the logging service existed -- but only by writing a
 * curl command and reading JSON. That is the wrong shape for the audience. The
 * reader has a dashboard; the party being asked to install a plugin and trust a
 * settlement figure did not.
 *
 * It matters beyond convenience. Settlement is the claim this whole network
 * makes. A publisher who cannot see what they are owed without a terminal is
 * trusting the figure rather than checking it, and the argument for a neutral
 * exchange is that both sides can audit it.
 *
 * == What is deliberately absent ==
 *
 * Retail prices and markup ratios. Not hidden by this page -- absent from the
 * response it renders. `pageClass` is what the publication asked and is owed;
 * what a reader actually paid includes their home base's margin, and the Rights
 * Owner is not entitled to see it. The endpoint returns totals grouped by home
 * base and nothing else, so there is no reader here to identify and no margin
 * here to leak. See #6, where a markup ratio did once reach a publisher report.
 *
 * @package Newshare_Network
 * @since   0.3.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_Earnings {

	/** Cached report, so refreshing the page does not re-ask the exchange. */
	private const CACHE = 'newshare_earnings_report';

	/** Short: a publisher watching a demonstration wants to see new reads appear. */
	private const CACHE_TTL = 120;

	/** Periods offered, in days. */
	private const PERIODS = array( 7, 30, 90 );

	public function register(): void {
		add_action( 'admin_menu', array( $this, 'add_page' ) );
	}

	public function add_page(): void {
		add_submenu_page(
			'options-general.php',
			__( 'Newshare Earnings', 'newshare-network' ),
			__( 'Newshare Earnings', 'newshare-network' ),
			'manage_options',
			'newshare-earnings',
			array( $this, 'render' )
		);
	}

	/**
	 * A URL under the logging service, whichever shape the endpoint is stored in.
	 *
	 * The default carries no path; what provisioning writes ends in "/log". #55
	 * was exactly this, in the credential check, where the mismatch produced a
	 * 404 that the code then treated as "nothing to report".
	 */
	private static function logging_url( string $path ): string {
		$base = untrailingslashit(
			(string) get_option( 'newshare_als_logging_endpoint', 'https://als.itega.org' )
		);
		if ( ! preg_match( '#/log$#', $base ) ) {
			$base .= '/log';
		}
		return $base . '/' . ltrim( $path, '/' );
	}

	/**
	 * Fetch the aggregated report for a period.
	 *
	 * @param int $days How far back to look.
	 * @return array{ok:bool,data:array<string,mixed>,error:string}
	 */
	private function report( int $days ): array {
		$key    = trim( (string) get_option( 'newshare_als_api_key', '' ) );
		$mbr_id = trim( (string) get_option( 'newshare_pub_mbr_id', '' ) );
		if ( '' === $key || '' === $mbr_id ) {
			return array(
				'ok'    => false,
				'data'  => array(),
				'error' => __( 'This site is not certified yet, so there is nothing to report. It certifies itself; if this persists, ITEGA cannot reach this domain.', 'newshare-network' ),
			);
		}

		$cache_key = self::CACHE . '_' . $days;
		$cached    = get_transient( $cache_key );
		if ( is_array( $cached ) ) {
			return array( 'ok' => true, 'data' => $cached, 'error' => '' );
		}

		$url = add_query_arg(
			array(
				'period_start' => gmdate( 'Y-m-d\TH:i:s\Z', time() - $days * DAY_IN_SECONDS ),
				'period_end'   => gmdate( 'Y-m-d\TH:i:s\Z' ),
			),
			self::logging_url( 'report/publisher/' . rawurlencode( $mbr_id ) )
		);

		$response = wp_remote_get(
			$url,
			array( 'timeout' => 15, 'headers' => array( 'X-API-Key' => $key ) )
		);

		if ( is_wp_error( $response ) ) {
			return array( 'ok' => false, 'data' => array(), 'error' => $response->get_error_message() );
		}

		$code = (int) wp_remote_retrieve_response_code( $response );
		$body = json_decode( wp_remote_retrieve_body( $response ), true );

		if ( 200 !== $code || ! is_array( $body ) ) {
			// Said plainly rather than as a status code: a publisher reading this
			// page has no way to act on "403" and every reason to want to know
			// whether the problem is theirs.
			$detail = 403 === $code
				? __( 'The exchange did not recognise this site. It re-certifies itself automatically; if this is still here tomorrow, tell ITEGA.', 'newshare-network' )
				: sprintf( /* translators: %d: HTTP status */ __( 'The exchange answered %d.', 'newshare-network' ), $code );
			return array( 'ok' => false, 'data' => array(), 'error' => $detail );
		}

		set_transient( $cache_key, $body, self::CACHE_TTL );
		return array( 'ok' => true, 'data' => $body, 'error' => '' );
	}

	private static function money( float $amount ): string {
		// Fractions of a cent are the point of this network; rounding a
		// settlement figure to two places is how #14 understated what a
		// publisher was owed.
		$s = rtrim( rtrim( number_format( $amount, 4, '.', '' ), '0' ), '.' );
		if ( false === strpos( $s, '.' ) ) {
			$s .= '.00';
		} elseif ( 1 === strlen( substr( strrchr( $s, '.' ), 1 ) ) ) {
			$s .= '0';
		}
		return '$' . $s;
	}

	public function render(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		$days = isset( $_GET['period'] ) ? (int) $_GET['period'] : 7;
		if ( ! in_array( $days, self::PERIODS, true ) ) {
			$days = 7;
		}

		$result = $this->report( $days );
		echo '<div class="wrap"><h1>' . esc_html__( 'Newshare Earnings', 'newshare-network' ) . '</h1>';

		echo '<p class="description">' . esc_html__(
			'What this publication is owed for network readers. These are the figures the exchange settles on, and they are yours to check rather than to take on trust.',
			'newshare-network'
		) . '</p>';

		echo '<p>';
		foreach ( self::PERIODS as $p ) {
			printf(
				'<a href="%s" class="button%s">%s</a> ',
				esc_url( add_query_arg( array( 'page' => 'newshare-earnings', 'period' => $p ), admin_url( 'options-general.php' ) ) ),
				$p === $days ? ' button-primary' : '',
				esc_html( sprintf( /* translators: %d: number of days */ __( 'Last %d days', 'newshare-network' ), $p ) )
			);
		}
		echo '</p>';

		if ( ! $result['ok'] ) {
			printf( '<div class="notice notice-warning"><p>%s</p></div></div>', esc_html( $result['error'] ) );
			return;
		}

		$data       = $result['data'];
		$aggregates = isset( $data['aggregates'] ) && is_array( $data['aggregates'] ) ? $data['aggregates'] : array();
		$owed       = 0.0;
		foreach ( $aggregates as $a ) {
			$owed += (float) ( $a['total_wholesale'] ?? 0 );
		}

		printf(
			'<h2 style="margin-bottom:0">%s</h2><p class="description">%s</p>',
			esc_html( self::money( $owed ) ),
			esc_html( sprintf(
				/* translators: 1: number of reads, 2: number of days */
				_n( 'from %1$s network read in the last %2$d days', 'from %1$s network reads in the last %2$d days',
					(int) ( $data['total_events'] ?? 0 ), 'newshare-network' ),
				number_format_i18n( (int) ( $data['total_events'] ?? 0 ) ),
				$days
			) )
		);

		if ( ! $aggregates ) {
			echo '<p>' . esc_html__( 'No network reads in this period yet.', 'newshare-network' ) . '</p></div>';
			return;
		}

		echo '<table class="widefat striped" style="max-width:44em"><thead><tr>';
		printf( '<th>%s</th><th style="text-align:right">%s</th><th style="text-align:right">%s</th></tr></thead><tbody>',
			esc_html__( 'Reader came from', 'newshare-network' ),
			esc_html__( 'Reads', 'newshare-network' ),
			esc_html__( 'Owed to you', 'newshare-network' )
		);
		foreach ( $aggregates as $a ) {
			printf(
				'<tr><td><code>%s</code></td><td style="text-align:right">%s</td><td style="text-align:right">%s</td></tr>',
				esc_html( (string) ( $a['home_base_id'] ?? '?' ) ),
				esc_html( number_format_i18n( (int) ( $a['total_events'] ?? 0 ) ) ),
				esc_html( self::money( (float) ( $a['total_wholesale'] ?? 0 ) ) )
			);
		}
		echo '</tbody></table>';

		echo '<p class="description" style="max-width:44em;margin-top:1em">' . esc_html__(
			'Grouped by the organization each reader has their account with. Individual readers are not shown here and cannot be: this publication receives an opaque identifier for each one, different at every publication, so there is nobody in these totals to name.',
			'newshare-network'
		) . '</p>';

		echo '<p class="description" style="max-width:44em">' . esc_html__(
			'These are wholesale figures — what you asked and are owed. What each reader paid also includes their own provider\'s margin, which is between them and it, and is not reported to you.',
			'newshare-network'
		) . '</p>';

		echo '</div>';
	}
}
