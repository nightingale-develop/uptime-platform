import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),

  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },

    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
    },

    {
      path: '/',
      component: AppLayout,
      meta: {
        requiresAuth: true,
      },
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },

        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
        },

        {
          path: 'monitors',
          name: 'monitors',
          component: () => import('@/views/MonitorsView.vue'),
        },

        {
          path: 'monitors/new',
          name: 'monitor-create',
          component: () => import('@/views/MonitorCreateView.vue'),
        },

        {
          path: 'monitors/:monitorId/edit',
          name: 'monitor-edit',
          component: () => import('@/views/MonitorEditView.vue'),
        },

        {
          path: 'monitors/:monitorId',
          name: 'monitor-details',
          component: () => import('@/views/MonitorDetailsView.vue'),
        },

        {
          path: 'incidents',
          name: 'incidents',
          component: () => import('@/views/IncidentsView.vue'),
        },

        {
          path: 'incidents/:incidentId',
          name: 'incident-details',
          component: () => import('@/views/IncidentDetailsView.vue'),
        },

        {
          path: 'maintenance',
          name: 'maintenance',
          component: () => import('@/views/MaintenanceView.vue'),
        },

        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
        },

        {
          path: 'status-pages',
          name: 'status-pages',
          component: () => import('@/views/StatusPagesView.vue'),
        },

        {
          path: 'status-pages/:pageId',
          name: 'status-page-details',
          component: () => import('@/views/StatusPageDetailsView.vue'),
        },

        {
          path: 'members',
          name: 'members',
          component: () => import('@/views/MembersView.vue'),
        },

        {
          path: 'organizations',
          name: 'organizations',
          component: () => import('@/views/OrganizationsView.vue'),
        },

        {
          path: 'api-keys',
          name: 'api-keys',
          component: () => import('@/views/ApiKeysView.vue'),
        },
      ],
    },

    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },

    {
      path: '/status/:slug',
      name: 'public-status-page',
      component: () => import('@/views/PublicStatusPageView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  if (!authStore.initialized) {
    await authStore.restoreSession()
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return {
      name: 'login',
      query: {
        redirect: to.fullPath,
      },
    }
  }

  if (authStore.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    return {
      name: 'dashboard',
    }
  }
})

export default router
