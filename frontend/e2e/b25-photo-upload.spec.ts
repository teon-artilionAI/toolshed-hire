/**
 * B2.5 signed-in photograph upload on staging.
 *
 * The local capture proved the upload control, the near-cap refusal and the
 * preview. It could not prove a real bucket write because the isolated API had
 * no credentials. This journey uses the protected staging runner's own session,
 * files a task-owned report on a returned Cape Town CBD rental, uploads a PNG
 * just below four mebibytes through the real counter screen, reads the stored
 * photograph, opens its signed link, and checks the audit event as the owner.
 * It resolves the report afterwards so the unit goes back on the shelf.
 */

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { nearCapPng } from './near-cap-photo.ts'
import { signInAsOwner, signInAsStaff, staffFor } from './staff.ts'
import { note, onStaging } from './staging.ts'

const BRANCH_CODE = 'CBD'
const WORKED_EXAMPLE_RENTAL = 'TSH-H-26-000098'
const WORKED_EXAMPLE_ASSET = 'TSH-DR-0042'
const PAGE_SIZE = 50
const CANDIDATE_LIMIT = 20
const MAX_PHOTO_BYTES = 4 * 1024 * 1024
const PHOTO_ACTION = 'damage_report.photo_added'
const RESOLUTION_COST = '120.00'
const REPORT_DESCRIPTION = 'A hairline crack in the housing was found during the staging photograph check.'

interface RentalItem {
  id: string
  assetTag: string | null
  returnedAt: string | null
  damageAssessment: string
}

interface Rental {
  reference: string
  items: RentalItem[]
}

interface RentalPage {
  items: Rental[]
}

interface DamageReport {
  id: string
  reference: string
}

interface Photo {
  id: string
  contentType: string
  sizeBytes: number
  uploadedAt: string
}

interface PhotoList {
  items: Photo[]
}

interface PhotoLink {
  url: string
  expiresAt: string
}

interface AuditEvent {
  actorName: string | null
  requestId: string | null
  afterState: Record<string, unknown>
}

interface AuditPage {
  items: AuditEvent[]
}

interface Candidate {
  rental: Rental
  item: RentalItem
}

type AuthHeaders = { Authorization: string }

let createdReport: DamageReport | null = null

async function bearer(request: APIRequestContext): Promise<AuthHeaders> {
  const response = await request.post('/api/auth/refresh')
  if (!response.ok()) {
    throw new Error(`POST /api/auth/refresh returned ${response.status()}: ${await response.text()}`)
  }
  const body = (await response.json()) as { accessToken?: string }
  if (body.accessToken === undefined || body.accessToken === '') {
    throw new Error('The refresh answer carried no access token.')
  }
  return { Authorization: `Bearer ${body.accessToken}` }
}

function candidateOf(rental: Rental, item: RentalItem): Candidate | null {
  if (item.assetTag === null || item.returnedAt === null || item.damageAssessment === 'REQUIRED') return null
  return { rental, item }
}

async function workedExampleCandidate(page: import('@playwright/test').Page, headers: AuthHeaders): Promise<Candidate | null> {
  const response = await page.request.get(`/api/rentals/${WORKED_EXAMPLE_RENTAL}`, { headers })
  if (response.status() === 404) return null
  if (!response.ok()) {
    throw new Error(`GET /api/rentals/${WORKED_EXAMPLE_RENTAL} returned ${response.status()}: ${await response.text()}`)
  }
  const rental = (await response.json()) as Rental
  const item = rental.items.find((each) => each.assetTag === WORKED_EXAMPLE_ASSET)
  return item === undefined ? null : candidateOf(rental, item)
}

async function listedCandidates(page: import('@playwright/test').Page, headers: AuthHeaders): Promise<Candidate[]> {
  const firstResponse = await page.request.get(
    `/api/rentals?branchCode=${BRANCH_CODE}&page=1&pageSize=${PAGE_SIZE}`,
    { headers },
  )
  if (!firstResponse.ok()) {
    throw new Error(`GET /api/rentals page 1 returned ${firstResponse.status()}: ${await firstResponse.text()}`)
  }
  const firstPage = (await firstResponse.json()) as RentalPage & { total: number }
  const lastPage = Math.max(1, Math.ceil(firstPage.total / PAGE_SIZE))
  const candidates: Candidate[] = []
  const seen = new Set<string>()
  for (let pageNumber = lastPage; pageNumber >= 1 && candidates.length < CANDIDATE_LIMIT; pageNumber -= 1) {
    const response = pageNumber === 1
      ? firstResponse
      : await page.request.get(`/api/rentals?branchCode=${BRANCH_CODE}&page=${pageNumber}&pageSize=${PAGE_SIZE}`, { headers })
    if (!response.ok()) {
      throw new Error(`GET /api/rentals page ${pageNumber} returned ${response.status()}: ${await response.text()}`)
    }
    const body = pageNumber === 1 ? firstPage : (await response.json()) as RentalPage
    for (const rental of body.items) {
      for (const item of rental.items) {
        const candidate = candidateOf(rental, item)
        if (candidate !== null && !seen.has(item.id)) {
          seen.add(item.id)
          candidates.push(candidate)
        }
      }
    }
  }
  return candidates
}

async function fileTaskOwnedReport(
  page: import('@playwright/test').Page,
  candidates: Candidate[],
  refusals: string[],
  headers: AuthHeaders,
): Promise<{ report: DamageReport; assetTag: string } | null> {
  for (const { rental, item } of candidates) {
    const response = await page.request.post('/api/damage-reports', {
      headers,
      data: {
        assetTag: item.assetTag,
        rentalItemId: item.id,
        severity: 'MINOR',
        description: REPORT_DESCRIPTION,
        repairEstimate: RESOLUTION_COST,
        chargeableToCustomer: false,
        recoveryAmount: null,
      },
    })
    if (response.status() === 201) {
      const report = (await response.json()) as DamageReport
      return { report, assetTag: item.assetTag ?? '' }
    }
    refusals.push(`${rental.reference}/${item.assetTag}: ${response.status()}`)
  }
  return null
}

test.afterEach(async ({ browser }, testInfo) => {
  if (createdReport === null) return
  const baseURL = testInfo.project.use.baseURL
  if (typeof baseURL !== 'string') {
    testInfo.annotations.push({ type: 'warning', description: 'No staging address was available to resolve the report.' })
    return
  }
  const context = await browser.newContext({ baseURL })
  try {
    const owner = await context.newPage()
    await signInAsOwner(owner)
    const headers = await bearer(owner.request)
    const response = await owner.request.post(`/api/damage-reports/${createdReport.id}/resolution`, {
      headers,
      data: {
        outcome: 'RESOLVED',
        actualRepairCost: RESOLUTION_COST,
        resolutionNotes: 'The housing was inspected and sealed after the staging photograph check.',
      },
    })
    if (!response.ok()) {
      testInfo.annotations.push({
        type: 'warning',
        description: `The task-owned report ${createdReport.reference} could not be resolved after the run: ${response.status()}.`,
      })
    }
  } catch (error) {
    testInfo.annotations.push({
      type: 'warning',
      description: `The task-owned report ${createdReport.reference} could not be resolved after the run: ${String(error)}.`,
    })
  } finally {
    createdReport = null
    await context.close()
  }
})

test('a signed-in assistant uploads a near-cap photograph and opens its signed link', { tag: '@staging' }, async ({
  page,
  browser,
  request,
}, testInfo) => {
  test.skip(!onStaging(), 'This photograph check runs on the staging project only.')

  const health = await request.get('/api/health')
  expect(health.ok()).toBe(true)
  const healthBody = (await health.json()) as {
    environment: string
    revision: string
    databaseReachable: boolean
  }
  expect(healthBody.environment).toBe('staging')
  expect(healthBody.databaseReachable).toBe(true)
  expect(healthBody.revision).toMatch(/^toolshed-api-staging-/)

  await signInAsStaff(page, staffFor(testInfo.project.name))
  const headers = await bearer(page.request)
  const refusals: string[] = []
  const known = await workedExampleCandidate(page, headers)
  let filed = known === null ? null : await fileTaskOwnedReport(page, [known], refusals, headers)
  if (filed === null) {
    const listed = await listedCandidates(page, headers)
    filed = await fileTaskOwnedReport(page, listed, refusals, headers)
  }
  if (filed === null) {
    throw new Error(`Could not file a task-owned damage report. ${refusals.join('; ')}`)
  }
  const { report, assetTag } = filed
  createdReport = report
  expect(report.reference).toMatch(/^TSH-D-\d{2}-\d{5}$/)

  await page.goto(`/counter/damage/${encodeURIComponent(assetTag)}`)
  await expect(page.getByRole('heading', { level: 1, name: 'Record damage' })).toBeVisible()
  const entry = page.getByRole('article', { name: report.reference })
  await expect(entry).toBeVisible()

  const png = nearCapPng()
  expect(png.length).toBeGreaterThan(3_900_000)
  expect(png.length).toBeLessThanOrEqual(MAX_PHOTO_BYTES)
  await entry.getByLabel(`Add a photograph to ${report.reference}`).setInputFiles({
    name: 'near-cap.png',
    mimeType: 'image/png',
    buffer: png,
  })
  await entry.getByRole('button', { name: `Upload the photograph to ${report.reference}` }).click()
  await expect(entry.getByText(`The photograph is added to ${report.reference}.`)).toBeVisible({
    timeout: 60_000,
  })

  const photoResponse = await page.request.get(`/api/damage-reports/${report.id}/photos`, { headers })
  expect(photoResponse.ok()).toBe(true)
  const photos = (await photoResponse.json()) as PhotoList
  expect(photos.items).toHaveLength(1)
  const photo = photos.items[0]
  expect(photo.contentType).toMatch(/^image\/(png|jpeg)$/)
  expect(photo.sizeBytes).toBeGreaterThan(0)
  expect(photo.uploadedAt).toBeTruthy()

  const linkResponse = await page.request.get(`/api/damage-reports/${report.id}/photos/${photo.id}`, { headers })
  expect(linkResponse.ok()).toBe(true)
  const link = (await linkResponse.json()) as PhotoLink
  expect(link.url).toContain('X-Goog-Signature')
  const remainingMs = Date.parse(link.expiresAt) - Date.now()
  expect(remainingMs).toBeGreaterThan(0)
  expect(remainingMs).toBeLessThanOrEqual(6 * 60 * 1000)

  const download = await request.get(link.url)
  expect(download.ok()).toBe(true)
  expect(download.headers()['content-type']).toMatch(/^image\/(png|jpeg)$/)
  expect((await download.body()).length).toBeGreaterThan(0)

  const baseURL = new URL(page.url()).origin
  const ownerContext = await browser.newContext({ baseURL })
  try {
    const owner = await ownerContext.newPage()
    await signInAsOwner(owner)
    const ownerHeaders = await bearer(owner.request)
    const auditUrl =
      `/api/admin/audit-events?entityType=damage_report&entityId=${report.id}` +
      `&action=${PHOTO_ACTION}&pageSize=10`
    await expect
      .poll(
        async () => {
          const response = await owner.request.get(auditUrl, { headers: ownerHeaders })
          if (!response.ok()) return 0
          return ((await response.json()) as AuditPage).items.length
        },
        { timeout: 20_000 },
      )
      .toBeGreaterThan(0)
    const auditResponse = await owner.request.get(auditUrl, { headers: ownerHeaders })
    expect(auditResponse.ok()).toBe(true)
    const audit = (await auditResponse.json()) as AuditPage
    const event = audit.items[0]
    expect(event.afterState.damage_photo_id).toBe(photo.id)
    expect(event.actorName).toBeTruthy()
    expect(event.requestId).toBeTruthy()

    const resolution = await owner.request.post(`/api/damage-reports/${report.id}/resolution`, {
      headers: ownerHeaders,
      data: {
        outcome: 'RESOLVED',
        actualRepairCost: RESOLUTION_COST,
        resolutionNotes: 'The housing was inspected and sealed after the staging photograph check.',
      },
    })
    expect(resolution.ok()).toBe(true)
    createdReport = null
  } finally {
    await ownerContext.close()
  }

  note(
    `B2.5 staging photograph passed for report ${report.reference} on ${assetTag} at revision ` +
      `${healthBody.revision}. The PNG was ${(png.length / 1024 / 1024).toFixed(2)} MiB, the stored ` +
      `photograph is ${photo.sizeBytes} bytes as ${photo.contentType}, the signed link expires in ` +
      `${Math.round(remainingMs / 1000)} s and the audit event ${PHOTO_ACTION} was read.`,
  )
})
