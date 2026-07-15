import { describe, expect, it } from 'vitest'

import { routes } from '../src/router'

describe('P1-1 route contract', () => {
  it('contains every real operator route', () => {
    expect(routes.map((route) => route.path)).toEqual(
      expect.arrayContaining([
        '/dashboard',
        '/tasks',
        '/tasks/new',
        '/approvals',
        '/tasks/:taskId/overview',
        '/tasks/:taskId/workflow',
        '/tasks/:taskId/materials',
        '/system/workers',
        '/system/outbox',
      ]),
    )
  })
})
