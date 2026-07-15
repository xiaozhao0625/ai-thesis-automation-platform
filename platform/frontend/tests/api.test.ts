import { describe, expect, it, vi } from 'vitest'

import { api } from '../src/api/client'

describe('real API client', () => {
  it('creates a task through POST /api/tasks', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'task-1', status: 'WAITING_FOR_APPROVAL' }), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await api.createTask({
      title: '实验室设备管理系统',
      capability_pack: 'python_web_management_v1',
      source_mount_path: 'benchmark/ingest-fixture-v1',
      created_by: 'operator-01',
    })

    expect(result.status).toBe('WAITING_FOR_APPROVAL')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('surfaces the stable backend error code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: 'SOURCE_PATH_NOT_ALLOWED', message: 'blocked', request_id: 'r1' },
          }),
          { status: 422, headers: { 'content-type': 'application/json' } },
        ),
      ),
    )

    await expect(api.getTask('missing')).rejects.toMatchObject({
      code: 'SOURCE_PATH_NOT_ALLOWED',
      requestId: 'r1',
    })
  })
})
