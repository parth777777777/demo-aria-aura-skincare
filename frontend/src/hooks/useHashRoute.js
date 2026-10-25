import { useEffect, useState } from 'react'

export function useHashRoute() {
  const [route, setRoute] = useState(window.location.hash === '#/summary' ? 'summary' : 'call')
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash === '#/summary' ? 'summary' : 'call')
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return [route, setRoute]
}
