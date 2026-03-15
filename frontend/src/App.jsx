import { useEffect, useState } from 'react'
import TestMode from './TestMode'

function App() {
  const [mode, setMode] = useState('user')
  const [restaurants, setRestaurants] = useState([])
  const [restaurantsLoading, setRestaurantsLoading] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [executionTime, setExecutionTime] = useState(null)
  const [restaurantId, setRestaurantId] = useState('')
  const [serviceDate, setServiceDate] = useState(new Date().toISOString().split('T')[0])
  const [restaurantData, setRestaurantData] = useState(null)
  const [loadingRestaurant, setLoadingRestaurant] = useState(false)
  const [isStadiumEvent, setIsStadiumEvent] = useState(false)
  const [isAzcaEvent, setIsAzcaEvent] = useState(false)
  const [starterResult, setStarterResult] = useState(null)
  const [starterLoading, setStarterLoading] = useState(false)
  const [mainResult, setMainResult] = useState(null)
  const [mainLoading, setMainLoading] = useState(false)
  const [dessertResult, setDessertResult] = useState(null)
  const [dessertLoading, setDessertLoading] = useState(false)
  const [menuFile, setMenuFile] = useState(null)
  const [menuUploadLoading, setMenuUploadLoading] = useState(false)
  const [menuUploadResult, setMenuUploadResult] = useState(null)
  
  // Campos de predicción (cargados automáticamente desde BD)
  const [capacityLimit, setCapacityLimit] = useState('')
  const [tableCount, setTableCount] = useState('')
  const [minServiceDuration, setMinServiceDuration] = useState('')
  const [terraceSetupType, setTerraceSetupType] = useState('')
  const [opensWeekends, setOpensWeekends] = useState(false)
  const [hasWifi, setHasWifi] = useState(false)
  const [restaurantSegment, setRestaurantSegment] = useState('')
  const [menuPrice, setMenuPrice] = useState('')
  const [distOfficeTowers, setDistOfficeTowers] = useState('')
  const [googleRating, setGoogleRating] = useState('')
  const [cuisineType, setCuisineType] = useState('')

  // Cargar restaurantes al iniciar
  useEffect(() => {
    console.log("🚀 App montado - Cargando restaurantes...")
    fetchRestaurants()
  }, [])

  useEffect(() => {
    setResult(null)
    setStarterResult(null)
    setMainResult(null)
    setDessertResult(null)
    setMenuUploadResult(null)
    setExecutionTime(null)
    setError(null)
  }, [restaurantId, serviceDate])

  useEffect(() => {
    if (restaurantId) {
      fetchRestaurantDetail(restaurantId)
    }
  }, [restaurantId])

  const fetchRestaurants = async () => {
    console.log("📍 fetchRestaurants() iniciado")
    setRestaurantsLoading(true)
    try {
      console.log("🌐 Llamando a GET /restaurants...")
      const response = await fetch('/restaurants')
      console.log(`📊 Response status: ${response.status}`)
      
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }
      
      const data = await response.json()
      const restaurantList = Array.isArray(data?.restaurants) ? data.restaurants : []
      console.log(`✅ Data recibida:`, data)
      console.log(`📦 Restaurantes: ${restaurantList.length} encontrados`)
      
      setRestaurants(restaurantList)
      if (restaurantList.length > 0) {
        const firstId = restaurantList[0].restaurant_id.toString()
        setRestaurantId(firstId)
        console.log(`✨ Primer restaurante seleccionado: ${restaurantList[0].name}`)
      }
    } catch (err) {
      console.error("❌ Error al cargar restaurantes:", err)
      setError(err.message)
    } finally {
      setRestaurantsLoading(false)
    }
  }

  const fetchRestaurantDetail = async (id) => {
    console.log(`📍 fetchRestaurantDetail(${id}) iniciado`)
    setLoadingRestaurant(true)
    try {
      console.log(`🌐 Llamando a GET /restaurants/${id}...`)
      const response = await fetch(`/restaurants/${id}`)
      console.log(`📊 Response status: ${response.status}`)
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const data = await response.json()
      console.log(`✅ Detalles del restaurante recibidos:`, data)
      setRestaurantData(data)
      
      // Rellenar los campos de predicción con los datos
      setCapacityLimit(data.capacity_limit || '')
      setTableCount(data.table_count || '')
      setMinServiceDuration(data.min_service_duration || '')
      setTerraceSetupType(data.terrace_setup_type || '')
      setOpensWeekends(data.opens_weekends || false)
      setHasWifi(data.has_wifi || false)
      setRestaurantSegment(data.restaurant_segment || '')
      setMenuPrice(data.menu_price || '')
      setDistOfficeTowers(data.dist_office_towers || '')
      setGoogleRating(data.google_rating || '')
      setCuisineType(data.cuisine_type || '')
      
      setError(null)
    } catch (err) {
      console.error(`❌ Error al cargar detalles del restaurante ${id}:`, err)
      setError(err.message)
    } finally {
      setLoadingRestaurant(false)
    }
  }

  const handleRestaurantChange = (e) => {
    const id = e.target.value
    setRestaurantId(id)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (!restaurantId) {
      setError("Por favor selecciona un restaurante")
      return
    }
    
    setLoading(true)
    setError(null)
    setResult(null)
    setExecutionTime(null)

    const startTime = performance.now()

    try {
      // Datos de predicción: solo restaurante y fecha
      // Los demás parámetros se calculan automáticamente en el backend:
      // - Parámetros de clima: desde Open-Meteo
      // - Parámetros de calendario: calculados automáticamente
      // - Datos históricos: desde fact_services
      // - Parámetros del restaurante: cargados de la BD
      const predictionData = {
        service_date: serviceDate,
        restaurant_id: parseInt(restaurantId),
        capacity_limit: capacityLimit ? parseInt(capacityLimit) : 80,
        table_count: tableCount ? parseInt(tableCount) : 20,
        min_service_duration: minServiceDuration ? parseInt(minServiceDuration) : 45,
        terrace_setup_type: terraceSetupType || 'standard',
        opens_weekends: opensWeekends,
        has_wifi: hasWifi,
        restaurant_segment: restaurantSegment || 'casual',
        menu_price: menuPrice ? parseFloat(menuPrice) : 25.50,
        dist_office_towers: distOfficeTowers ? parseInt(distOfficeTowers) : 500,
        google_rating: googleRating ? parseFloat(googleRating) : 4.5,
        cuisine_type: cuisineType || 'mediterranean',
        // Eventos que proporciona el usuario
        is_stadium_event: isStadiumEvent,
        is_azca_event: isAzcaEvent,
      }

      console.log("🚀 Enviando predicción (backend completará datos automáticamente):", predictionData)

      const response = await fetch('/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(predictionData)
      })

      const endTime = performance.now()
      setExecutionTime(Math.round(endTime - startTime))

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`)
      const data = await response.json()
      console.log("✅ Predicción exitosa:", data)
      setResult(data)
    } catch (err) {
      console.error("❌ Error en predicción:", err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handlePredictStarter = async (e) => {
    e.preventDefault()
    
    if (!restaurantId) {
      setError("Por favor selecciona un restaurante")
      return
    }
    
    setStarterLoading(true)
    setError(null)
    setStarterResult(null)

    try {
      const starterData = {
        restaurant_id: parseInt(restaurantId),
        service_date: serviceDate,
      }

      console.log("🍽️ Prediciendo starters:", starterData)

      const response = await fetch('/predict/starter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(starterData)
      })

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`)
      const data = await response.json()
      console.log("✅ Starters predichos:", data)
      setStarterResult(data)
    } catch (err) {
      console.error("❌ Error prediciendo starters:", err)
      setError(err.message)
    } finally {
      setStarterLoading(false)
    }
  }

  const handlePredictMain = async (e) => {
    e.preventDefault()
    
    if (!restaurantId) {
      setError("Por favor selecciona un restaurante")
      return
    }
    
    setMainLoading(true)
    setError(null)
    setMainResult(null)

    try {
      const mainData = {
        restaurant_id: parseInt(restaurantId),
        service_date: serviceDate,
      }

      console.log("🍖 Prediciendo platos principales:", mainData)

      const response = await fetch('/predict/main', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mainData)
      })

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`)
      const data = await response.json()
      console.log("✅ Platos principales predichos:", data)
      setMainResult(data)
    } catch (err) {
      console.error("❌ Error prediciendo mains:", err)
      setError(err.message)
    } finally {
      setMainLoading(false)
    }
  }

  const handlePredictDessert = async (e) => {
    e.preventDefault()
    
    if (!restaurantId) {
      setError("Por favor selecciona un restaurante")
      return
    }
    
    setDessertLoading(true)
    setError(null)
    setDessertResult(null)

    try {
      const dessertData = {
        restaurant_id: parseInt(restaurantId),
        service_date: serviceDate,
      }

      console.log("🍰 Prediciendo postres:", dessertData)

      const response = await fetch('/predict/dessert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dessertData)
      })

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`)
      const data = await response.json()
      console.log("✅ Postres predichos:", data)
      setDessertResult(data)
    } catch (err) {
      console.error("❌ Error prediciendo desserts:", err)
      setError(err.message)
    } finally {
      setDessertLoading(false)
    }
  }

  const handlePredictMenuUpload = async (e) => {
    e.preventDefault()

    if (!restaurantId) {
      setError("Por favor selecciona un restaurante")
      return
    }

    if (!menuFile) {
      setError("Sube un archivo de menú antes de predecir")
      return
    }

    setMenuUploadLoading(true)
    setError(null)
    setResult(null)
    setStarterResult(null)
    setMainResult(null)
    setDessertResult(null)
    setExecutionTime(null)
    setMenuUploadResult(null)

    try {
      const formData = new FormData()
      formData.append('menu_file', menuFile)

      console.log("📄 Subiendo menú para OCR (solo extracción)...")

      const response = await fetch('/ocr/menu-sections', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        let message = `HTTP error: ${response.status}`
        try {
          const payload = await response.json()
          if (payload?.detail) message = payload.detail
        } catch {
          // no-op
        }
        throw new Error(message)
      }

      const data = await response.json()
      console.log("✅ Menú extraído por OCR:", data)
      setMenuUploadResult(data)
    } catch (err) {
      console.error("❌ Error en OCR del menú:", err)
      setError(err.message)
    } finally {
      setMenuUploadLoading(false)
    }
  }

  if (mode === 'test') {
    return <TestMode onBack={() => setMode('user')} />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex flex-col">
      {/* Header */}
      <div className="border-b border-purple-500/30 bg-gradient-to-r from-slate-900/95 to-purple-900/95 backdrop-blur-md sticky top-0 z-50">
        <div className="w-full px-4 sm:px-6 py-4 sm:py-6">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl sm:text-4xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent truncate">
                🍽️ AML-Cousine
              </h1>
              <p className="text-purple-300/80 text-xs sm:text-sm mt-1 sm:mt-2 truncate">Demand Forecasting</p>
            </div>
            <button
              onClick={() => setMode('test')}
              className="px-3 sm:px-6 py-2 sm:py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-semibold text-xs sm:text-base rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 whitespace-nowrap"
            >
              ⚙️ Admin
            </button>
          </div>
        </div>
      </div>

      {/* Main Content - Centro vertical */}
      <div className="flex-1 flex items-center justify-center w-full px-4 py-6 sm:py-12">
        <div className="w-full max-w-4xl">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 sm:gap-8">
            {/* Formulario - 2 columnas en desktop */}
            <div className="lg:col-span-2">
              <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-6">
                {/* Seleccionar Restaurante */}
                <div className="bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/30 backdrop-blur-sm rounded-xl p-4 sm:p-6">
                  <label className="block text-sm sm:text-base font-semibold text-blue-200 mb-3">
                    🏪 Restaurante
                  </label>
                  <select
                    value={restaurantId}
                    onChange={handleRestaurantChange}
                    disabled={loading || restaurantsLoading}
                    className="w-full px-3 sm:px-4 py-2 sm:py-3 bg-slate-800/50 border border-blue-400/50 rounded-lg text-white focus:outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-500/30 placeholder-slate-400 transition-all duration-200 disabled:opacity-50 text-sm sm:text-base"
                  >
                    <option value="">
                      {restaurantsLoading ? 'Cargando restaurantes...' : restaurants.length === 0 ? 'No hay restaurantes disponibles' : 'Elige un restaurante'}
                    </option>
                    {restaurants.map((r) => (
                      <option key={r.restaurant_id} value={r.restaurant_id.toString()}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                  {loadingRestaurant && <p className="text-blue-300 text-xs sm:text-sm mt-2">⏳ Cargando datos del restaurante...</p>}
                </div>

                {/* Seleccionar Fecha */}
                <div className="bg-gradient-to-br from-purple-500/20 to-pink-500/20 border border-purple-500/30 backdrop-blur-sm rounded-xl p-4 sm:p-6">
                  <label className="block text-sm sm:text-base font-semibold text-purple-200 mb-3">
                    📅 Fecha de Predicción
                  </label>
                  <input
                    type="date"
                    value={serviceDate}
                    onChange={(e) => setServiceDate(e.target.value)}
                    disabled={loading}
                    className="w-full px-3 sm:px-4 py-2 sm:py-3 bg-slate-800/50 border border-purple-400/50 rounded-lg text-white focus:outline-none focus:border-purple-300 focus:ring-2 focus:ring-purple-500/30 transition-all duration-200 disabled:opacity-50 text-sm sm:text-base"
                  />
                </div>

                {/* Eventos */}
                <div className="bg-gradient-to-br from-orange-500/20 to-red-500/20 border border-orange-500/30 backdrop-blur-sm rounded-xl p-4 sm:p-6">
                  <p className="text-orange-300 text-xs sm:text-sm font-semibold mb-4 uppercase tracking-wide">🎪 Eventos del Día</p>
                  
                  <div className="space-y-3 sm:space-y-4">
                    {/* Evento Estadio */}
                    <label className="flex items-center gap-3 cursor-pointer p-2 sm:p-3 rounded-lg hover:bg-white/5 transition">
                      <input
                        type="checkbox"
                        checked={isStadiumEvent}
                        onChange={(e) => setIsStadiumEvent(e.target.checked)}
                        disabled={loading}
                        className="w-5 h-5 rounded border-2 border-orange-400/50 bg-slate-800/50 cursor-pointer accent-orange-500 transition"
                      />
                      <div className="flex-1">
                        <div className="text-orange-200 text-xs sm:text-sm font-semibold">Evento Estadio ⚽</div>
                        <div className="text-orange-300/70 text-xs">¿Hay evento de fútbol?</div>
                      </div>
                      <span className="text-orange-300 text-xs sm:text-sm font-medium bg-orange-500/20 px-2 sm:px-3 py-1 rounded">
                        {isStadiumEvent ? 'Sí' : 'No'}
                      </span>
                    </label>

                    {/* Evento AZCA */}
                    <label className="flex items-center gap-3 cursor-pointer p-2 sm:p-3 rounded-lg hover:bg-white/5 transition">
                      <input
                        type="checkbox"
                        checked={isAzcaEvent}
                        onChange={(e) => setIsAzcaEvent(e.target.checked)}
                        disabled={loading}
                        className="w-5 h-5 rounded border-2 border-orange-400/50 bg-slate-800/50 cursor-pointer accent-orange-500 transition"
                      />
                      <div className="flex-1">
                        <div className="text-orange-200 text-xs sm:text-sm font-semibold">Evento AZCA 🏢</div>
                        <div className="text-orange-300/70 text-xs">¿Hay evento en AZCA?</div>
                      </div>
                      <span className="text-orange-300 text-xs sm:text-sm font-medium bg-orange-500/20 px-2 sm:px-3 py-1 rounded">
                        {isAzcaEvent ? 'Sí' : 'No'}
                      </span>
                    </label>
                  </div>
                </div>

                {/* Menú OCR */}
                <div className="bg-gradient-to-br from-fuchsia-500/20 to-violet-500/20 border border-fuchsia-500/30 backdrop-blur-sm rounded-xl p-4 sm:p-6">
                  <label className="block text-sm sm:text-base font-semibold text-fuchsia-200 mb-3">
                    📄 Menú (OCR Document Intelligence)
                  </label>

                  <input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg,.webp"
                    onChange={(e) => {
                      const selected = e.target.files && e.target.files[0] ? e.target.files[0] : null
                      setMenuFile(selected)
                    }}
                    disabled={menuUploadLoading}
                    className="w-full px-3 sm:px-4 py-2 sm:py-3 bg-slate-800/50 border border-fuchsia-400/50 rounded-lg text-white file:mr-3 file:px-3 file:py-1 file:rounded-md file:border-0 file:bg-fuchsia-600 file:text-white focus:outline-none focus:border-fuchsia-300 focus:ring-2 focus:ring-fuchsia-500/30 transition-all duration-200 disabled:opacity-50 text-sm sm:text-base"
                  />

                  <p className="text-fuchsia-300/70 text-xs mt-2">
                    Sube PDF o imagen del menú para ver qué detecta como entrante, principal y postre.
                  </p>

                  <button
                    type="button"
                    onClick={handlePredictMenuUpload}
                    disabled={menuUploadLoading || !menuFile}
                    className="mt-4 w-full py-2 sm:py-3 bg-gradient-to-r from-fuchsia-600 via-violet-600 to-indigo-600 hover:from-fuchsia-500 hover:via-violet-500 hover:to-indigo-500 text-white font-bold text-xs sm:text-base rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1 sm:gap-2"
                  >
                    {menuUploadLoading ? (
                      <span className="animate-spin text-sm sm:text-base">⏳</span>
                    ) : (
                      <>
                        <span className="text-sm sm:text-lg">🧠</span>
                        <span className="hidden sm:inline">OCR Secciones</span>
                        <span className="sm:hidden text-xs">OCR</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Botones */}
                <div className="grid grid-cols-2 sm:grid-cols-2 gap-2 sm:gap-3">
                  <button
                    type="submit"
                    disabled={loading || !restaurantId || restaurants.length === 0}
                    className="py-2 sm:py-3 bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 hover:from-blue-500 hover:via-purple-500 hover:to-pink-500 text-white font-bold text-xs sm:text-base rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1 sm:gap-2"
                  >
                    {loading ? (
                      <span className="animate-spin text-sm sm:text-base">⏳</span>
                    ) : (
                      <>
                        <span className="text-sm sm:text-lg">🚀</span>
                        <span className="hidden sm:inline">Demanda</span>
                        <span className="sm:hidden text-xs">Demand</span>
                      </>
                    )}
                  </button>
                  
                  <button
                    type="button"
                    onClick={handlePredictStarter}
                    disabled={starterLoading || !restaurantId || restaurants.length === 0}
                    className="py-2 sm:py-3 bg-gradient-to-r from-amber-600 via-orange-600 to-red-600 hover:from-amber-500 hover:via-orange-500 hover:to-red-500 text-white font-bold text-xs sm:text-base rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1 sm:gap-2"
                  >
                    {starterLoading ? (
                      <span className="animate-spin text-sm sm:text-base">⏳</span>
                    ) : (
                      <>
                        <span className="text-sm sm:text-lg">🍽️</span>
                        <span className="hidden sm:inline">Starters</span>
                        <span className="sm:hidden text-xs">Start</span>
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={handlePredictMain}
                    disabled={mainLoading || !restaurantId || restaurants.length === 0}
                    className="py-2 sm:py-3 bg-gradient-to-r from-green-600 via-emerald-600 to-teal-600 hover:from-green-500 hover:via-emerald-500 hover:to-teal-500 text-white font-bold text-xs sm:text-base rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1 sm:gap-2"
                  >
                    {mainLoading ? (
                      <span className="animate-spin text-sm sm:text-base">⏳</span>
                    ) : (
                      <>
                        <span className="text-sm sm:text-lg">🍖</span>
                        <span className="hidden sm:inline">Mains</span>
                        <span className="sm:hidden text-xs">Main</span>
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={handlePredictDessert}
                    disabled={dessertLoading || !restaurantId || restaurants.length === 0}
                    className="py-2 sm:py-3 bg-gradient-to-r from-rose-600 via-pink-600 to-red-600 hover:from-rose-500 hover:via-pink-500 hover:to-red-500 text-white font-bold text-xs sm:text-base rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1 sm:gap-2"
                  >
                    {dessertLoading ? (
                      <span className="animate-spin text-sm sm:text-base">⏳</span>
                    ) : (
                      <>
                        <span className="text-sm sm:text-lg">🍰</span>
                        <span className="hidden sm:inline">Desserts</span>
                        <span className="sm:hidden text-xs">Desst</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>

            {/* Panel de Resultados - 1 columna */}
            <div className="lg:col-span-1 space-y-4 sm:space-y-6">
              {error && (
                <div className="bg-gradient-to-br from-red-500/20 to-orange-500/20 border border-red-500/50 backdrop-blur-sm rounded-xl p-4 sm:p-6">
                  <p className="text-red-300 font-semibold mb-2 text-sm sm:text-base">⚠️ Error Demanda</p>
                  <p className="text-red-200 text-xs sm:text-sm">{error}</p>
                </div>
              )}

              {/* Resultado Demanda */}
              {result ? (
                <div className="bg-gradient-to-br from-emerald-500/20 to-teal-500/20 border border-emerald-500/50 backdrop-blur-sm rounded-xl p-4 sm:p-8">
                  <div className="text-center mb-6 sm:mb-8">
                    <p className="text-emerald-300/70 text-xs sm:text-sm font-semibold uppercase tracking-wide mb-2 sm:mb-3">
                      Predicción Demanda
                    </p>
                    <p className="text-4xl sm:text-6xl font-bold bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">
                      {result.prediction_result}
                    </p>
                    <p className="text-emerald-300/70 text-xs sm:text-sm mt-2 sm:mt-3">servicios esperados</p>
                  </div>

                  <div className="space-y-3 sm:space-y-4 border-t border-emerald-500/30 pt-4 sm:pt-6">
                    <div className="flex justify-between items-center">
                      <span className="text-emerald-300/70 text-xs sm:text-sm">Confianza</span>
                      <span className="text-emerald-400 font-bold text-xs sm:text-sm">85%</span>
                    </div>
                    <div className="w-full h-2 bg-emerald-900/50 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full" style={{ width: '85%' }}></div>
                    </div>

                    <div className="space-y-2 sm:space-y-3 border-t border-emerald-500/30 pt-3 sm:pt-4 text-xs sm:text-sm">
                      <div className="flex justify-between items-start gap-2">
                        <span className="text-emerald-300/70">Versión</span>
                        <span className="text-emerald-200 font-mono text-right">{result.model_version || 'v1.0'}</span>
                      </div>
                      <div className="flex justify-between items-start gap-2">
                        <span className="text-emerald-300/70">Tiempo</span>
                        <span className="text-emerald-200 font-mono">{executionTime}ms</span>
                      </div>
                      <div className="flex justify-between items-start gap-2">
                        <span className="text-emerald-300/70">Log</span>
                        <span className="text-emerald-200 font-mono text-right truncate">#{result.log_id}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* Resultado Starters */}
              {starterResult ? (
                <div className="bg-gradient-to-br from-amber-500/20 to-orange-500/20 border border-amber-500/50 backdrop-blur-sm rounded-xl p-4 sm:p-8">
                  <div className="text-center mb-6 sm:mb-8">
                    <p className="text-amber-300/70 text-xs sm:text-sm font-semibold uppercase tracking-wide mb-2 sm:mb-3">
                      Top 3 Starters
                    </p>
                    <p className="text-amber-300 text-sm sm:text-base">Recomendaciones para los primeros</p>
                  </div>

                  <div className="space-y-3 sm:space-y-4">
                    {starterResult.top_3_dishes && starterResult.top_3_dishes.map((dish) => (
                      <div key={dish.rank} className="bg-amber-900/30 rounded-lg p-3 sm:p-4 border border-amber-500/30 hover:border-amber-400/50 transition-all">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-amber-400 to-orange-400 bg-clip-text text-transparent">
                              #{dish.rank}
                            </span>
                            <span className="text-amber-200 font-semibold text-sm sm:text-base">{dish.name}</span>
                          </div>
                          <span className="text-amber-400 font-bold text-sm sm:text-base">
                            {Math.round(dish.score * 100)}%
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 bg-amber-900/50 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-amber-500 to-orange-400 rounded-full" 
                            style={{ width: `${dish.score * 100}%` }}
                          ></div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 sm:space-y-3 border-t border-amber-500/30 pt-3 sm:pt-4 text-xs sm:text-sm mt-4 sm:mt-6">
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-amber-300/70">Modelo</span>
                      <span className="text-amber-200 font-mono text-right">{starterResult.model_version}</span>
                    </div>
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-amber-300/70">Fecha Predicción</span>
                      <span className="text-amber-200 font-mono">{starterResult.service_date}</span>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* Resultado Mains */}
              {mainResult ? (
                <div className="bg-gradient-to-br from-green-500/20 to-emerald-500/20 border border-green-500/50 backdrop-blur-sm rounded-xl p-4 sm:p-8">
                  <div className="text-center mb-6 sm:mb-8">
                    <p className="text-green-300/70 text-xs sm:text-sm font-semibold uppercase tracking-wide mb-2 sm:mb-3">
                      Top 3 Platos Principales
                    </p>
                    <p className="text-green-300 text-sm sm:text-base">Recomendaciones para los segundos</p>
                  </div>

                  <div className="space-y-3 sm:space-y-4">
                    {mainResult.top_3_dishes && mainResult.top_3_dishes.map((dish) => (
                      <div key={dish.rank} className="bg-green-900/30 rounded-lg p-3 sm:p-4 border border-green-500/30 hover:border-green-400/50 transition-all">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-green-400 to-emerald-400 bg-clip-text text-transparent">
                              #{dish.rank}
                            </span>
                            <span className="text-green-200 font-semibold text-sm sm:text-base">{dish.name}</span>
                          </div>
                          <span className="text-green-400 font-bold text-sm sm:text-base">
                            {Math.round(dish.score * 100)}%
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 bg-green-900/50 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-green-500 to-emerald-400 rounded-full" 
                            style={{ width: `${dish.score * 100}%` }}
                          ></div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 sm:space-y-3 border-t border-green-500/30 pt-3 sm:pt-4 text-xs sm:text-sm mt-4 sm:mt-6">
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-green-300/70">Modelo</span>
                      <span className="text-green-200 font-mono text-right">{mainResult.model_version}</span>
                    </div>
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-green-300/70">Fecha Predicción</span>
                      <span className="text-green-200 font-mono">{mainResult.service_date}</span>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* Resultado Desserts */}
              {dessertResult ? (
                <div className="bg-gradient-to-br from-rose-500/20 to-pink-500/20 border border-rose-500/50 backdrop-blur-sm rounded-xl p-4 sm:p-8">
                  <div className="text-center mb-6 sm:mb-8">
                    <p className="text-rose-300/70 text-xs sm:text-sm font-semibold uppercase tracking-wide mb-2 sm:mb-3">
                      Top 3 Postres
                    </p>
                    <p className="text-rose-300 text-sm sm:text-base">Recomendaciones para los postres</p>
                  </div>

                  <div className="space-y-3 sm:space-y-4">
                    {dessertResult.top_3_dishes && dessertResult.top_3_dishes.map((dish) => (
                      <div key={dish.rank} className="bg-rose-900/30 rounded-lg p-3 sm:p-4 border border-rose-500/30 hover:border-rose-400/50 transition-all">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-rose-400 to-pink-400 bg-clip-text text-transparent">
                              #{dish.rank}
                            </span>
                            <span className="text-rose-200 font-semibold text-sm sm:text-base">{dish.name}</span>
                          </div>
                          <span className="text-rose-400 font-bold text-sm sm:text-base">
                            {Math.round(dish.score * 100)}%
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 bg-rose-900/50 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-rose-500 to-pink-400 rounded-full" 
                            style={{ width: `${dish.score * 100}%` }}
                          ></div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 sm:space-y-3 border-t border-rose-500/30 pt-3 sm:pt-4 text-xs sm:text-sm mt-4 sm:mt-6">
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-rose-300/70">Modelo</span>
                      <span className="text-rose-200 font-mono text-right">{dessertResult.model_version}</span>
                    </div>
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-rose-300/70">Fecha Predicción</span>
                      <span className="text-rose-200 font-mono">{dessertResult.service_date}</span>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* Resultado OCR + Menú */}
              {menuUploadResult ? (
                <div className="bg-gradient-to-br from-fuchsia-500/20 to-violet-500/20 border border-fuchsia-500/50 backdrop-blur-sm rounded-xl p-4 sm:p-8">
                  <div className="text-center mb-6 sm:mb-8">
                    <p className="text-fuchsia-300/70 text-xs sm:text-sm font-semibold uppercase tracking-wide mb-2 sm:mb-3">
                      OCR Menú
                    </p>
                    <p className="text-fuchsia-300 text-sm sm:text-base">Detección visual por secciones</p>
                  </div>

                  <div className="space-y-2 text-xs sm:text-sm mb-5 pb-4 border-b border-fuchsia-500/30">
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-fuchsia-300/70">OCR</span>
                      <span className="text-fuchsia-200 font-mono text-right">{menuUploadResult.ocr_provider}</span>
                    </div>
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-fuchsia-300/70">Entrante detectado</span>
                      <span className="text-fuchsia-200 text-right">{menuUploadResult.extracted_menu?.starter}</span>
                    </div>
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-fuchsia-300/70">Principal detectado</span>
                      <span className="text-fuchsia-200 text-right">{menuUploadResult.extracted_menu?.main}</span>
                    </div>
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-fuchsia-300/70">Postre detectado</span>
                      <span className="text-fuchsia-200 text-right">{menuUploadResult.extracted_menu?.dessert}</span>
                    </div>
                  </div>

                  <div className="space-y-4 mb-5 pb-4 border-b border-fuchsia-500/30">
                    {[
                      {
                        title: 'Opciones OCR de entrantes',
                        items: menuUploadResult.extracted_menu?.starter_options,
                      },
                      {
                        title: 'Opciones OCR de principales',
                        items: menuUploadResult.extracted_menu?.main_options,
                      },
                      {
                        title: 'Opciones OCR de postres',
                        items: menuUploadResult.extracted_menu?.dessert_options,
                      },
                    ].map((group) => (
                      <div key={group.title} className="bg-fuchsia-950/20 rounded-lg border border-fuchsia-500/20 p-3 sm:p-4">
                        <p className="text-fuchsia-200 font-semibold text-xs sm:text-sm mb-2">{group.title}</p>
                        {group.items?.length ? (
                          <div className="space-y-1">
                            {group.items.map((item, index) => (
                              <div key={`${group.title}-${index}-${item}`} className="text-fuchsia-100 text-xs sm:text-sm flex items-start gap-2">
                                <span className="text-fuchsia-300 leading-5">•</span>
                                <span>{item}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-fuchsia-300/70 text-xs sm:text-sm">Sin líneas detectadas para este bloque</p>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 sm:space-y-3 border-t border-fuchsia-500/30 pt-3 sm:pt-4 text-xs sm:text-sm mt-4 sm:mt-6">
                    <div className="flex justify-between items-start gap-2">
                      <span className="text-fuchsia-300/70">Ejecución</span>
                      <span className="text-fuchsia-200 font-mono text-right">{menuUploadResult.execution_timestamp || '-'}</span>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* Placeholder */}
              {!result && !starterResult && !mainResult && !dessertResult && !menuUploadResult && (
                <div className="bg-gradient-to-br from-slate-700/50 to-slate-600/50 border border-slate-500/30 backdrop-blur-sm rounded-xl p-4 sm:p-8 text-center">
                  <p className="text-slate-400 text-xs sm:text-sm">💡 Completa el formulario</p>
                  <p className="text-slate-400 text-xs sm:text-sm">y presiona cualquiera de los botones</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
