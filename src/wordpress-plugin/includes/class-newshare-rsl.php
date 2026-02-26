<?php
/**
 * Newshare RSL (Resource Specification Language) JSON-LD Tagging.
 *
 * Injects structured metadata into post pages so the network can
 * discover content pricing, licensing, and publisher identity.
 *
 * @package Newshare_Network
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Newshare_RSL {

	/**
	 * Inject RSL JSON-LD metadata into the <head> on single posts.
	 *
	 * Hooked to `wp_head`.
	 */
	public function inject_rsl_metadata(): void {
		if ( ! is_singular( 'post' ) ) {
			return;
		}

		$post = get_post();
		if ( ! $post ) {
			return;
		}

		$pub_mbr_id = get_option( 'newshare_pub_mbr_id', '' );

		// Page class: per-post override, then site default.
		$page_class = get_post_meta( $post->ID, 'newshare_page_class', true );
		if ( '' === $page_class || false === $page_class ) {
			$page_class = get_option( 'newshare_default_page_class', '0.05' );
		}
		$page_class = (float) $page_class;

		// RSL tag: per-post override, then site default.
		$rsl_tag = get_post_meta( $post->ID, 'newshare_rsl_tag', true );
		if ( empty( $rsl_tag ) ) {
			$rsl_tag = get_option( 'newshare_default_rsl_tag', 'CC-BY-NC' );
		}

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
			'newshare:pageClass' => $page_class,
			'newshare:pubMbrId'  => $pub_mbr_id,
			'newshare:rslTag'    => $rsl_tag,
		);

		/**
		 * Filters the RSL metadata before output.
		 *
		 * @param array   $metadata The RSL metadata array.
		 * @param WP_Post $post     The current post object.
		 */
		$metadata = apply_filters( 'newshare_rsl_metadata', $metadata, $post );

		$json = wp_json_encode( $metadata, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT );

		if ( $json ) {
			echo "\n<!-- Newshare Network RSL Metadata -->\n";
			echo '<script type="application/ld+json">' . "\n";
			// wp_json_encode already handles escaping for JSON context.
			// phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
			echo $json;
			echo "\n</script>\n";
		}
	}
}
