/**
 * API client — wraps axios calls to the PathGen backend.
 * Uses Vite proxy (/api → http://localhost:8000/api)
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

export async function analyzeCode(sourceCode, functionName = 'main', language = 'c') {
  const { data } = await api.post('/analyze', {
    source_code: sourceCode,
    function_name: functionName,
    language: language,
  })
  return data
}

export async function generateTests(sourceCode, functionName = 'main', language = 'c', options = {}) {
  const { data } = await api.post('/generate-tests', {
    source_code: sourceCode,
    function_name: functionName,
    language: language,
    max_paths: options.maxPaths ?? null,
    max_loop_iterations: options.maxLoopIters ?? null,
  })
  return data
}

export async function getHistory(limit = 20, offset = 0) {
  const { data } = await api.get('/history', { params: { limit, offset } })
  return data
}

export async function getHistoryRun(id) {
  const { data } = await api.get(`/history/${id}`)
  return data
}
