import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('frontend build hygiene', () => {
  it('type-checks without emitting config files that shadow TypeScript', () => {
    const packageJson = JSON.parse(readFileSync(resolve('package.json'), 'utf8'))

    expect(packageJson.scripts.build).toContain('vue-tsc -b --noEmit')
    for (const path of [
      'vite.config.js',
      'vite.config.d.ts',
      'playwright.config.js',
      'playwright.config.d.ts',
    ]) {
      expect(existsSync(resolve(path)), path).toBe(false)
    }
  })
})
