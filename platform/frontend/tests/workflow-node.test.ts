import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WorkflowNode from '../src/components/WorkflowNode.vue'

describe('WorkflowNode', () => {
  it('shows Chinese name, technical key and attempt count', () => {
    const wrapper = mount(WorkflowNode, {
      props: {
        node: {
          id: 'node-1',
          node_key: 'material_ingest',
          display_name: '资料摄取',
          status: 'RUNNING',
          attempt_count: 1,
          max_attempts: 3,
          current_output_count: 0,
        },
      },
    })
    expect(wrapper.text()).toContain('资料摄取')
    expect(wrapper.text()).toContain('material_ingest')
    expect(wrapper.text()).toContain('Attempt 1 / 3')
  })
})
