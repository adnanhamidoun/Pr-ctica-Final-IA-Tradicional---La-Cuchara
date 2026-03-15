import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { RestaurantDetail } from '../../types/domain'

type PredictedDish = {
  rank: number
  name: string
  score: number
  estimated_count: number
}

type CoursePredictionResponse = {
  top_3_dishes: PredictedDish[]
}

type ServicePredictionResponse = {
  prediction_result: number
}

type MenuPredictionState = {
  starters: PredictedDish[]
  mains: PredictedDish[]
  desserts: PredictedDish[]
}

const emptyPredictions: MenuPredictionState = {
  starters: [],
  mains: [],
  desserts: [],
}

export default function MenuView() {
  const { restaurantId } = useParams()
  const [restaurant, setRestaurant] = useState<RestaurantDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [menuPredictions, setMenuPredictions] = useState<MenuPredictionState>(emptyPredictions)
  const [menuLoading, setMenuLoading] = useState(false)
  const [menuError, setMenuError] = useState('')
  const [servicePrediction, setServicePrediction] = useState<number | null>(null)
  const [serviceError, setServiceError] = useState('')

  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const [selectedDate, setSelectedDate] = useState(today)

  const restaurantIdNumber = useMemo(() => {
    const parsed = Number(restaurantId)
    return Number.isFinite(parsed) ? parsed : null
  }, [restaurantId])

  useEffect(() => {
    if (!restaurantIdNumber) {
      setError('ID de restaurante inválido.')
      setLoading(false)
      return
    }

    const loadRestaurant = async () => {
      try {
        setLoading(true)
        const response = await fetch(`/restaurants/${restaurantIdNumber}`)
        if (!response.ok) throw new Error('No se pudo cargar el restaurante seleccionado.')

        const data = (await response.json()) as RestaurantDetail
        setRestaurant(data)
        setError('')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'No se pudo cargar el restaurante seleccionado.')
      } finally {
        setLoading(false)
      }
    }

    loadRestaurant()
  }, [restaurantIdNumber])

  useEffect(() => {
    if (!restaurantIdNumber || !restaurant) return

    const loadPredictedData = async () => {
      try {
        setMenuLoading(true)
        setMenuError('')
        setServiceError('')

        const coursePayload = {
          restaurant_id: restaurantIdNumber,
          service_date: selectedDate,
        }

        const servicePayload = {
          service_date: selectedDate,
          restaurant_id: restaurantIdNumber,
          is_stadium_event: false,
          is_azca_event: false,
          capacity_limit: restaurant.capacity_limit ?? 60,
          table_count: restaurant.table_count ?? 15,
          min_service_duration: restaurant.min_service_duration ?? 45,
          terrace_setup_type: restaurant.terrace_setup_type ?? 'outdoor',
          opens_weekends: Boolean(restaurant.opens_weekends),
          has_wifi: Boolean(restaurant.has_wifi),
          restaurant_segment: restaurant.restaurant_segment ?? 'business',
          menu_price: restaurant.menu_price ?? 20,
          dist_office_towers: restaurant.dist_office_towers ?? 500,
          google_rating: restaurant.google_rating ?? 4.2,
          cuisine_type: restaurant.cuisine_type ?? 'mediterranean',
        }

        const [serviceRes, starterRes, mainRes, dessertRes] = await Promise.all([
          fetch('/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(servicePayload),
          }),
          fetch('/predict/starter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(coursePayload),
          }),
          fetch('/predict/main', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(coursePayload),
          }),
          fetch('/predict/dessert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(coursePayload),
          }),
        ])

        if (!serviceRes.ok) {
          throw new Error('No se pudo generar la predicción de servicios para este restaurante.')
        }

        if (!starterRes.ok || !mainRes.ok || !dessertRes.ok) {
          throw new Error('No se pudieron generar las predicciones del menú para este restaurante.')
        }

        const [serviceData, starterData, mainData, dessertData] = (await Promise.all([
          serviceRes.json(),
          starterRes.json(),
          mainRes.json(),
          dessertRes.json(),
        ])) as [ServicePredictionResponse, CoursePredictionResponse, CoursePredictionResponse, CoursePredictionResponse]

        setServicePrediction(serviceData.prediction_result ?? null)

        setMenuPredictions({
          starters: starterData.top_3_dishes ?? [],
          mains: mainData.top_3_dishes ?? [],
          desserts: dessertData.top_3_dishes ?? [],
        })
      } catch (err) {
        setMenuPredictions(emptyPredictions)
        setServicePrediction(null)
        const message = err instanceof Error ? err.message : 'No se pudieron obtener las predicciones del restaurante.'
        if (message.toLowerCase().includes('servicio')) {
          setServiceError(message)
        } else {
          setMenuError(message)
        }
      } finally {
        setMenuLoading(false)
      }
    }

    loadPredictedData()
  }, [restaurantIdNumber, selectedDate, restaurant])

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text)]">Menú Predicho por IA</h2>
          <p className="text-sm text-[var(--text-muted)]">
            Predicción automática para entrante, principal y postre según el modelo y la fecha elegida.
          </p>
        </div>

        <Link
          to="/cliente/restaurantes"
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-medium text-[var(--text)] transition-all duration-200 hover:bg-[var(--surface-soft)]"
        >
          Volver al listado
        </Link>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm text-[var(--text-muted)]">Restaurante seleccionado</p>
            {loading ? <p className="text-sm text-[var(--text-muted)]">Cargando restaurante...</p> : null}
            {error ? <p className="text-sm text-[#E53935]">{error}</p> : null}
            {!loading && !error ? (
              <div className="mt-1 space-y-1">
                <h3 className="text-lg font-bold text-[var(--text)]">{restaurant?.name}</h3>
                <p className="text-xs text-[var(--text-muted)]">Fecha de predicción: {selectedDate}</p>
                <p className="text-xs text-[var(--text-muted)]">
                  Precio medio menú: €{(restaurant?.menu_price ?? 20).toFixed(2)}
                </p>
              </div>
            ) : null}
          </div>

          <label className="space-y-1">
            <span className="text-xs font-medium text-[var(--text-muted)]">Elegir fecha</span>
            <input
              type="date"
              value={selectedDate}
              onChange={(event) => setSelectedDate(event.target.value)}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[var(--accent)]"
            />
          </label>
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-sm">
        <h4 className="font-semibold text-[var(--text)]">Predicción de servicios</h4>
        {menuLoading ? <p className="mt-2 text-sm text-[var(--text-muted)]">Calculando demanda de servicios...</p> : null}
        {!menuLoading && serviceError ? <p className="mt-2 text-sm text-[#E53935]">{serviceError}</p> : null}
        {!menuLoading && !serviceError && servicePrediction !== null ? (
          <p className="mt-2 text-sm text-[var(--text)]">
            Servicios estimados para el día seleccionado: <span className="font-bold">{servicePrediction}</span>
          </p>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { title: 'Entrantes', items: menuPredictions.starters },
          { title: 'Principales', items: menuPredictions.mains },
          { title: 'Postres', items: menuPredictions.desserts },
        ].map((section) => (
          <div key={section.title} className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <h4 className="font-semibold text-[var(--text)]">{section.title}</h4>

            {menuLoading ? <p className="mt-2 text-sm text-[var(--text-muted)]">Generando predicción...</p> : null}

            {!menuLoading && menuError ? <p className="mt-2 text-sm text-[#E53935]">{menuError}</p> : null}

            {!menuLoading && !menuError && section.items.length === 0 ? (
              <p className="mt-2 text-sm text-[var(--text-muted)]">Sin predicciones para mostrar.</p>
            ) : null}

            {!menuLoading && !menuError && section.items.length > 0 ? (
              <ul className="mt-3 space-y-2">
                {section.items.map((dish) => (
                  <li key={`${section.title}-${dish.rank}-${dish.name}`} className="rounded-xl border border-[var(--border)]/70 bg-[var(--surface-soft)]/50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--text)]">#{dish.rank} {dish.name}</p>
                      <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-xs text-[var(--text-muted)]">
                        {(dish.score * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">
                      Precio menú: €{(restaurant?.menu_price ?? 20).toFixed(2)}
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">Demanda estimada: {dish.estimated_count}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}
