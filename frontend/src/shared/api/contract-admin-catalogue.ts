/**
 * The admin catalogue wire types. The categories and the product models as
 * the owner manages them, with the rates, the deposit, the late fee and the
 * replacement value of each model, and whether customers see it.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * The generated request bodies say less than the server allows in two ways,
 * and the types below say it exactly. An edit may send null only for a
 * category's `description` and `parentCategoryId` and a model's
 * `longDescription`, which clears them. The server refuses null for any other
 * field, naming it, so here every other field of an edit is a value or left
 * out. And a field with a default on the server is generated as required, so
 * `isPublished` appears in the body of a new model. The server refuses true
 * there, because a new model starts unpublished, and the screen sends neither
 * value, so it is left out here. Publishing has a route of its own.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type {
  BodyOf,
  CreatedJsonOf,
  IsoTimestamp,
  JsonOf,
  Money,
  Paths,
  QueryOf,
  Refine,
} from './contract-kit'

type CategoriesRoute = Paths['/api/admin/categories']
type CategoryRoute = Paths['/api/admin/categories/{id}']
type ModelsRoute = Paths['/api/admin/models']
type ModelRoute = Paths['/api/admin/models/{id}']
type PublicationRoute = Paths['/api/admin/models/{id}/publication']

/**
 * One category as the owner sees it, switched on or off. The list, a new
 * category and a change all answer with this, so it is built from all three.
 *
 * `parentCategoryId` and `parentName` are null for a top level category.
 * Nesting stops at two levels, so a parent never has a parent of its own.
 * `description` is null when the category has none. `modelCount` is the
 * number of models the category holds itself, published or not.
 */
export type AdminCategory = JsonOf<CategoriesRoute['get']>['items'][number] &
  CreatedJsonOf<CategoriesRoute['post']> &
  JsonOf<CategoryRoute['patch']>

/**
 * The query `GET /api/admin/categories` accepts. The list is paged like every
 * other, and one page of the largest size holds every category a hire
 * business keeps. The generated type lets the page and its size be left out,
 * and the screen always sends both, so here they are required.
 */
export type AdminCategoryQuery = Refine<QueryOf<CategoriesRoute['get']>, { page: number; pageSize: number }>

/** `GET /api/admin/categories`. Every category, switched on or not, each
 *  parent before its children. */
export type AdminCategoryList = Refine<JsonOf<CategoriesRoute['get']>, { items: AdminCategory[] }>

/**
 * The body `POST /api/admin/categories` accepts. A new category starts
 * switched on. A parent must itself be at the top level, and a code or a slug
 * already in use is refused, each with a 422 naming the field. The generated
 * type lets the description and the parent be left out, and the screen
 * always sends both, null for none, so here they are required.
 */
export type NewCategoryRequest = Refine<
  BodyOf<CategoriesRoute['post']>,
  { description: string | null; parentCategoryId: string | null }
>

/** The body `PATCH /api/admin/categories/{id}` accepts. Any of the fields of a
 *  new category, and whether it is switched on. A field left out keeps its
 *  value, and null clears the description or makes the category top level. */
export type CategoryChangesRequest = Refine<
  BodyOf<CategoryRoute['patch']>,
  { code?: string; name?: string; slug?: string; sortOrder?: number; isActive?: boolean }
>

/**
 * One product model as the owner sees it, published or not. Its read, the
 * list, a new model, a change and a publication all answer with this, so it
 * is built from all five.
 *
 * The rates are per unit and exclude VAT. `replacementValue` caps what a
 * damage charge for one unit can come to. `longDescription` is null when the
 * model has none. `assetCount` is how many units of it the fleet holds. Each
 * booking and hire keeps its own copy of the figures, so a change here never
 * reaches one already made.
 */
export type AdminModel = Refine<
  JsonOf<ModelRoute['get']> &
    JsonOf<ModelsRoute['get']>['items'][number] &
    CreatedJsonOf<ModelsRoute['post']> &
    JsonOf<ModelRoute['patch']> &
    JsonOf<PublicationRoute['post']>,
  {
    dailyRate: Money
    weeklyRate: Money
    depositAmount: Money
    lateFeePerDay: Money
    replacementValue: Money
    updatedAt: IsoTimestamp
  }
>

/**
 * The query `GET /api/admin/models` accepts.
 *
 * `q` is free text of at least two characters, matched against the stock
 * code, the name, the manufacturer and the model number. `published` true
 * lists the published models only and false the hidden ones only. Every
 * filter may be left out. The generated type lets the page and its size be
 * left out, and the screen always sends both, so here they are required.
 */
export type AdminModelQuery = Refine<QueryOf<ModelsRoute['get']>, { page: number; pageSize: number }>

/** `GET /api/admin/models`. One page of the models that match, by name. */
export type AdminModelPage = Refine<JsonOf<ModelsRoute['get']>, { items: AdminModel[] }>

/**
 * The body `POST /api/admin/models` accepts. Every field of a model except the
 * ones the server keeps itself and whether it is published, which a new model
 * never is. The server refuses a stock code or a slug already in use, money
 * below zero, a weekly rate above seven days at the daily rate, a shortest
 * hire above the longest and a category that is switched off, each with a 422
 * naming the field. The screen always sends the full description, null for
 * none, so here it is required.
 */
export type NewModelRequest = Refine<
  Omit<BodyOf<ModelsRoute['post']>, 'isPublished'>,
  {
    longDescription: string | null
    dailyRate: Money
    weeklyRate: Money
    depositAmount: Money
    lateFeePerDay: Money
    replacementValue: Money
  }
>

/**
 * The body `PATCH /api/admin/models/{id}` accepts. Any field of a new model.
 * The stock code is not among them, because it never changes once the model
 * exists, and the server refuses it naming `sku`. The route would also take
 * `isPublished`, and it is left out here so that showing and hiding a model
 * always goes through the publication route. A field left out keeps its
 * value, and null clears the full description.
 */
export type ModelChangesRequest = Refine<
  Omit<BodyOf<ModelRoute['patch']>, 'isPublished'>,
  {
    name?: string
    slug?: string
    categoryId?: string
    manufacturer?: string
    modelNumber?: string
    shortDescription?: string
    dailyRate?: Money
    weeklyRate?: Money
    depositAmount?: Money
    lateFeePerDay?: Money
    replacementValue?: Money
    minHireDays?: number
    maxHireDays?: number
  }
>

/** The body `POST /api/admin/models/{id}/publication` accepts. True shows the
 *  model to customers and false hides it. Asking for what the model already
 *  is changes nothing and answers with the model as it is. */
export type PublicationRequest = BodyOf<PublicationRoute['post']>
