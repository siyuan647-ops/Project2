import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '../views/HomePage.vue'
import AdvisorView from '../views/AdvisorView.vue'
import CreditView from '../views/CreditView.vue'

const routes = [
  { path: '/', name: 'Home', component: HomePage },
  { path: '/advisor', name: 'Advisor', component: AdvisorView },
  { path: '/credit', name: 'Credit', component: CreditView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
