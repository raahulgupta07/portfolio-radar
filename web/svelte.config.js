import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter(),
		// Content Security Policy: scripts only from this site (SvelteKit adds hashes for its own inline script).
		csp: {
			mode: 'auto',
			directives: {
				'default-src': ['self'],
				'script-src': ['self'],
				'style-src': ['self', 'unsafe-inline', 'https://fonts.googleapis.com'],
				'font-src': ['self', 'https://fonts.gstatic.com'],
				'img-src': ['self', 'data:'],
				'connect-src': ['self'],
				'frame-ancestors': ['none'],
				// Sign-in and sign-out forms redirect to the SSO server (Entra, or Keycloak at City's own address).
				'form-action': ['self', 'https:', 'http://localhost:*'],
				'base-uri': ['self'],
				'object-src': ['none']
			}
		}
	}
};

export default config;
