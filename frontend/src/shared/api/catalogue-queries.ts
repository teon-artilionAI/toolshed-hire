/**
 * The catalogue and availability reads, as cached queries.
 *
 * A screen does not call the endpoint functions directly. It asks for one of
 * these and hands it to `useQuery`, so every screen that wants the same data
 * shares one request and one cached answer.
 *
 * The first segment of each key decides how fresh the data is. Keys that start
 * with the catalogue segment are fresh for a minute, and keys that start with
 * the availability segment are never fresh. Those rules live in
 * query-client.ts, and the key is all a query needs to get the right one.
 *
 * Each read passes on the signal it is given, so a request for a search the
 * customer has already moved on from is abandoned and not left to finish.
 */

import { queryOptions } from '@tanstack/react-query'
import {
  getModel,
  getModelAvailability,
  listBranches,
  listCategories,
  listModels,
  searchAvailability,
} from './catalogue'
import type { AvailabilityQuery, ModelAvailabilityQuery, ModelListQuery } from './contract'
import { AVAILABILITY_KEY, CATALOGUE_KEY } from './query-client'

export const catalogueQueries = {
  /** The three branches. */
  branches: () =>
    queryOptions({
      queryKey: [CATALOGUE_KEY, 'branches'],
      queryFn: ({ signal }) => listBranches(signal),
    }),

  /** Every category, parents before children. */
  categories: () =>
    queryOptions({
      queryKey: [CATALOGUE_KEY, 'categories'],
      queryFn: ({ signal }) => listCategories(signal),
    }),

  /** One page of models, with no availability. */
  models: (query: ModelListQuery) =>
    queryOptions({
      queryKey: [CATALOGUE_KEY, 'models', query],
      queryFn: ({ signal }) => listModels(query, signal),
    }),

  /** One model by its slug. */
  model: (slug: string) =>
    queryOptions({
      queryKey: [CATALOGUE_KEY, 'model', slug],
      queryFn: ({ signal }) => getModel(slug, signal),
    }),

  /** One page of models with a yes or no from every branch for the period. */
  availability: (query: AvailabilityQuery) =>
    queryOptions({
      queryKey: [AVAILABILITY_KEY, 'search', query],
      queryFn: ({ signal }) => searchAvailability(query, signal),
    }),

  /** One model, a quantity and a period, with a yes or no from every branch. */
  modelAvailability: (slug: string, query: ModelAvailabilityQuery) =>
    queryOptions({
      queryKey: [AVAILABILITY_KEY, 'model', slug, query],
      queryFn: ({ signal }) => getModelAvailability(slug, query, signal),
    }),
}
