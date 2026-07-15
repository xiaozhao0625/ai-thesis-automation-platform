import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import ApprovalsPage from './pages/ApprovalsPage.vue'
import DashboardPage from './pages/DashboardPage.vue'
import MaterialsPage from './pages/MaterialsPage.vue'
import NewTaskPage from './pages/NewTaskPage.vue'
import OutboxPage from './pages/OutboxPage.vue'
import TaskOverviewPage from './pages/TaskOverviewPage.vue'
import TasksPage from './pages/TasksPage.vue'
import WorkflowPage from './pages/WorkflowPage.vue'
import WorkersPage from './pages/WorkersPage.vue'

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', component: DashboardPage },
  { path: '/tasks', component: TasksPage },
  { path: '/tasks/new', component: NewTaskPage },
  { path: '/approvals', component: ApprovalsPage },
  { path: '/tasks/:taskId/overview', component: TaskOverviewPage },
  { path: '/tasks/:taskId/workflow', component: WorkflowPage },
  { path: '/tasks/:taskId/materials', component: MaterialsPage },
  { path: '/system/workers', component: WorkersPage },
  { path: '/system/outbox', component: OutboxPage },
]

export const router = createRouter({ history: createWebHistory(), routes })
