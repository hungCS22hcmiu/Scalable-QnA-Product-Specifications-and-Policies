import React from 'react'
import ReactDOM from 'react-dom/client'
import { createHashRouter, RouterProvider } from 'react-router-dom'
import ProductList from './pages/ProductList.jsx'
import ProductChat from './pages/ProductChat.jsx'
import './styles.css'

// HASH router, not browser router. The gateway has an SPA fallback, but the demo is driven by
// opening and duplicating many tabs by hand, and a hash route survives copy-paste and reload
// identically wherever it is served from. One less thing that can fail on stage.
const router = createHashRouter([
  { path: '/', element: <ProductList /> },
  { path: '/p/:docId', element: <ProductChat /> },
])

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
