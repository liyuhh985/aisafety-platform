import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'
import './map-tile-fix.css'

const app = createApp(App)
app.use(router)
app.mount('#app')
