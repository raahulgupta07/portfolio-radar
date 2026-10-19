// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {
		interface User {
			id: string;
			name: string;
			kind: 'human' | 'agent' | 'service';
			roles: string[];
		}
		interface Locals {
			user: User | null;
			token: string | null;
		}
		interface Error {
			message: string;
		}
	}
}

export {};
