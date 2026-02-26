<?php
/**
 * Newshare RSL (Really Simple Licensing) JSON-LD Metadata Tagging.
 *
 * This class injects structured JSON-LD metadata into post pages so that the
 * Newshare Network infrastructure (ALS, home bases, and crawlers) can discover:
 *   - Content pricing (pageClass -- the wholesale price set by the publisher)
 *   - Publisher identity (pubMbrId -- the publisher's network member ID)
 *   - Licensing terms (rslTag -- e.g., CC-BY-NC, per the RSL standard)
 *   - Standard Schema.org NewsArticle metadata (headline, dates, publisher)
 *
 * RSL (Really Simple Licensing) is defined at rslstandard.org and provides a
 * lightweight way for publishers to tag content with machine-readable rights
 * and pricing information, similar to how robots.txt works for crawling rules.
 *
 * The JSON-LD is injected into the HTML <head> as a <script type="application/ld+json">
 * block, following Google's structured data recommendations.
 *
 * Per-post overrides: Editors can set pageClass and rslTag on individual posts
 * via the Newshare Access Control meta box. If not set, site-wide defaults from
 * the plugin settings are used.
 *
 * @package Newshare_Network
 * @since   0.1.0
 * @see     https://rslstandard.org/
 * @see     https://schema.org/NewsArticle
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_RSL {

	// =========================================================================
	// JSON-LD Metadata Injection
	// =========================================================================

	/**
	 * Inject RSL JSON-LD metadata into the <head> on single posts.
	 *
	 * Builds a Schema.org NewsArticle object with Newshare-specific extensions
	 * (newshare:pageClass, newshare:pubMbrId, newshare:rslTag) and outputs it
	 * as a JSON-LD script block.
	 *
	 * Hooked to: wp_head
	 */
	public function inject_rsl_metadata(): void {
		// Only inject metadata on single post pages -- not archives, pages, or feeds.
		if ( ! is_singular( 'post' ) ) {
			return;
		}

		$post = get_post();
		if ( ! $post ) {
			return;
		}

		$pub_mbr_id = get_option( 'newshare_pub_mbr_id', '' );

		// -----------------------------------------------------------------
		// Page class (wholesale price): per-post override takes precedence
		// over the site-wide default. This is the dollar amount the publisher
		// charges the network for each content access event.
		// -----------------------------------------------------------------
		$page_class = get_post_meta( $post->ID, 'newshare_page_class', true );
		if ( '' === $page_class || false === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}
		$page_class = (float) $page_class;

		// -----------------------------------------------------------------
		// RSL tag (license): per-post override takes precedence over the
		// site-wide default. Common values: CC-BY-NC, CC-BY, All-Rights-Reserved.
		// -----------------------------------------------------------------
		$rsl_tag = get_post_meta( $post->ID, 'newshare_rsl_tag', true );
		if ( empty( $rsl_tag ) ) {
			$rsl_tag = get_option( 'newshare_default_rsl_tag', 'CC-BY-NC' );
		}

		// Build the Schema.org NewsArticle metadata with Newshare extensions.
		$metadata = array(
			'@context'           => 'https://schema.org',
			'@type'              => 'NewsArticle',
			'identifier'         => get_permalink( $post->ID ),
			'dateCreated'        => get_the_date( 'c', $post ),
			'datePublished'      => get_the_date( 'c', $post ),
			'dateModified'       => get_the_modified_date( 'c', $post ),
			'headline'           => get_the_title( $post ),
			'publisher'          => array(
				'@type'      => 'Organization',
				'name'       => get_bloginfo( 'name' ),
				'identifier' => $pub_mbr_id,
			),
			// Newshare-specific extensions (namespaced with "newshare:" prefix).
			'newshare:pageClass' => $page_class,
			'newshare:pubMbrId'  => $pub_mbr_id,
			'newshare:rslTag'    => $rsl_tag,
		);

		/**
		 * Filters the RSL metadata before output.
		 *
		 * Allows themes or other plugins to add or modify the JSON-LD metadata.
		 * For example, adding author information or custom Newshare fields.
		 *
		 * @param array   $metadata The RSL metadata array.
		 * @param WP_Post $post     The current post object.
		 */
		$metadata = apply_filters( 'newshare_rsl_metadata', $metadata, $post );

		// -----------------------------------------------------------------
		// FIX (MAJOR): Prevent XSS via </script> injection in post titles.
		//
		// If a post title contains the string "</script>", it would break out
		// of the JSON-LD script block and allow arbitrary HTML/JS injection.
		//
		// Previously, JSON_UNESCAPED_SLASHES was used which made this worse
		// by preserving the forward slash in "</script>". Now we:
		//   1. Encode with JSON_UNESCAPED_UNICODE (but NOT JSON_UNESCAPED_SLASHES)
		//      so forward slashes are escaped as \/ by default.
		//   2. As a defense-in-depth measure, we also explicitly replace any
		//      "</script>" sequences that might appear (e.g., from Unicode
		//      normalization or other edge cases).
		//
		// The resulting JSON is safe to embed inside a <script> block because
		// all "</script" sequences are neutralized.
		// -----------------------------------------------------------------
		$json = wp_json_encode( $metadata, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT );

		if ( $json ) {
			// Defense-in-depth: escape any </script> sequences that could break
			// out of the JSON-LD block. The forward slash escaping above should
			// already handle this, but we double-check as a safety net.
			$json = str_replace( '</', '<\/', $json );

			echo "\n<!-- Newshare Network RSL Metadata -->\n";
			echo '<script type="application/ld+json">' . "\n";
			// phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- JSON-LD context, escaped above.
			echo $json;
			echo "\n</script>\n";
		}
	}
}
