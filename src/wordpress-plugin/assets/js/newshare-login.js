/**
 * Newshare Network — Login button interaction.
 *
 * Handles the click on the "Network Login" button and provides minimal
 * UI feedback during the redirect to the ALS.
 *
 * @package Newshare_Network
 */

( function () {
	'use strict';

	document.addEventListener( 'DOMContentLoaded', function () {
		var buttons = document.querySelectorAll( '.newshare-login-btn' );

		buttons.forEach( function ( button ) {
			button.addEventListener( 'click', function ( e ) {
				// If it is a link, let the browser follow it.
				if ( button.tagName === 'A' && button.href ) {
					button.textContent = 'Connecting to network\u2026';
					button.style.opacity = '0.7';
					button.style.pointerEvents = 'none';
					return;
				}

				// For form-based buttons, prevent double-clicks.
				if ( button.dataset.clicked ) {
					e.preventDefault();
					return;
				}
				button.dataset.clicked = 'true';
				button.textContent = 'Connecting to network\u2026';
				button.style.opacity = '0.7';
			} );
		} );
	} );
} )();
