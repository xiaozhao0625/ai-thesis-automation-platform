import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StatusBadge from '../src/components/StatusBadge.vue'

describe('StatusBadge', () => {
  it.each([
    ['RUNNING', '运行中', 'running'],
    ['SUCCEEDED', '已完成', 'success'],
    ['WAITING_FOR_APPROVAL', '待审批', 'waiting'],
    ['FAILED', '失败', 'danger'],
  ])('maps %s to Chinese label and tone', (status, label, tone) => {
    const wrapper = mount(StatusBadge, { props: { status } })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.classes()).toContain(`status--${tone}`)
  })
})
