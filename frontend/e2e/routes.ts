/**
 * The public screens the browser tests visit, with the heading that proves
 * each one has finished loading.
 *
 * Screens load lazily, so a test that looks at the page straight after
 * navigating would see the loading skeleton. Waiting for the top level heading
 * is how I know the real screen is on the page.
 */

export interface PublicRoute {
  path: string
  heading: string
}

export const CATALOGUE_HOME: PublicRoute = {
  path: '/',
  heading: 'Hire tools and plant across Cape Town',
}

export const SEARCH: PublicRoute = {
  path: '/search',
  heading: 'What is free for your dates',
}

export const SIGN_IN: PublicRoute = {
  path: '/signin',
  heading: 'Sign in to Toolshed Hire',
}

export const REGISTER: PublicRoute = {
  path: '/register',
  heading: 'Create your hire account',
}

export const PRIVACY: PublicRoute = {
  path: '/privacy',
  heading: 'Privacy notice',
}
