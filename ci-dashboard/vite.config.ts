import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * In a live build the dashboard reads Supabase through /api/*, and the
 * build-time snapshot has no reason to be in dist at all — it is 21.2 MB of
 * real customer records, and shipping it to Vercel puts it at a hashed URL
 * behind nothing but Deployment Protection.
 *
 * Marking the branch unreachable is not enough. services/index.ts already
 * resolves the mode from a literal Vite substitutes at build time, and the
 * bundler still kept realService and still emitted the 21.2 MB chunk —
 * measured, not assumed. Aliasing the module out is the only way to be sure the
 * snapshot never enters the graph.
 */
const LIVE = process.env.VITE_DATA_MODE === 'live'
const realServiceAlias = LIVE
  ? [{
      find: /^\.\/realService$/,
      replacement: fileURLToPath(new URL('./src/services/realService.live-stub.ts', import.meta.url)),
    }]
  : []

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: { alias: realServiceAlias },
  server: {
    watch: {
      // dist-real/ and dist-live/ are build output: thousands of per-call JSON
      // files under OneDrive, which locks them mid-sync. Watching them adds
      // nothing and kills the dev server outright with EBUSY when a lock lands.
      ignored: ['**/dist/**', '**/dist-real/**', '**/dist-live/**'],
    },
  },
})
