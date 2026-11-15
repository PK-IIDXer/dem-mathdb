import { ja } from './messages/ja'
import { en } from './messages/en'
import { getLanguage } from './language'

export type MessageKey = keyof typeof ja
type Args<K extends MessageKey> = typeof ja[K] extends (...args: infer A) => string ? A : []

/** Pure display lookup. Never use translated text for requests or branching. */
export function t<K extends MessageKey>(key: K, ...args: Args<K>): string {
  const message = (getLanguage() === 'ja' ? ja : en)[key]
  return typeof message === 'function' ? (message as (...values: unknown[]) => string)(...args) : message
}

const publicSetMessageKeys = new Map<string, readonly [MessageKey, MessageKey]>([
  ['0daf185d-cb58-57a3-8533-b9c3f7e46026', ['publicEmptySetName', 'publicEmptySetDescription']],
  ['8c36c258-671b-5749-a47d-b11c2618d762', ['publicEmptyIsSetName', 'publicEmptyIsSetDescription']],
  ['8e1484ff-b9cc-5909-9de3-ccba334fced8', ['publicEmptyHasNoElementsName', 'publicEmptyHasNoElementsDescription']],
  ['3f70bd31-1f80-58d9-b6f3-0116e3fffc0d', ['publicEmptyUniqueName', 'publicEmptyUniqueDescription']],
  ['4acb1a67-2266-5aae-8837-0a891877aa65', ['publicNonemptyHasElementName', 'publicNonemptyHasElementDescription']],
  ['557304de-d064-5def-996d-32118d018f54', ['publicEmptyNotSingletonName', 'publicEmptyNotSingletonDescription']],
  ['abd98b7d-cef0-5c81-bc62-2662d706c39f', ['publicEmptyClassUniqueName', 'publicEmptyClassUniqueDescription']],
  ['4f391acf-aa0e-560a-ab8a-be24dd1c57ba', ['publicRelationDefinition1Name', 'publicRelationDefinition1Description']],
  ['cfbe2291-1387-5857-85a6-c8fffbf666da', ['publicRelationDefinition2Name', 'publicRelationDefinition2Description']],
  ['7cbd6c9f-a924-5d9d-afb9-2f851d0c865d', ['publicRelationDefinition3Name', 'publicRelationDefinition3Description']],
  ['2651dbd9-0b54-5df1-86e2-589a26d62b64', ['publicRelationDefinition4Name', 'publicRelationDefinition4Description']],
  ['7a5903af-a90d-52ad-b1ac-bb42f56d99c1', ['publicRelationDefinition5Name', 'publicRelationDefinition5Description']],
  ['17478805-0c66-5832-8fa9-ac7713b16d6e', ['publicRelationDefinition6Name', 'publicRelationDefinition6Description']],
  ['33192b33-f834-51e0-a966-d406dd4f37eb', ['publicRelationDefinition7Name', 'publicRelationDefinition7Description']],
  ['403a61e1-d953-518a-a3e8-b2495ec73e42', ['publicRelationTheorem1Name', 'publicRelationTheorem1Description']],
  ['e054b314-9469-59cb-a40b-909311d84665', ['publicRelationTheorem2Name', 'publicRelationTheorem2Description']],
  ['e565ebc3-7ce0-578e-be51-5c6f69191674', ['publicRelationTheorem3Name', 'publicRelationTheorem3Description']],
  ['44d18ce6-b8ac-501d-a9fd-0cf999a342ce', ['publicRelationTheorem4Name', 'publicRelationTheorem4Description']],
  ['b10a2097-e429-5e0f-b459-c43d6c34516d', ['publicRelationTheorem5Name', 'publicRelationTheorem5Description']],
  ['63629f99-6af7-52a4-aa08-49fa540f94ca', ['publicRelationTheorem6Name', 'publicRelationTheorem6Description']],
  ['275c2f75-eb48-509c-be23-aed6cbab79fe', ['publicRelationTheorem7Name', 'publicRelationTheorem7Description']],
  ['478a5839-fb58-5012-9c61-ec2343a6cbca', ['publicRelationTheorem8Name', 'publicRelationTheorem8Description']],
  ['d16ca9fc-b1b6-54f9-92d8-93754f1c22a1', ['publicRelationTheorem9Name', 'publicRelationTheorem9Description']],
  ['66f20dbc-fd66-5319-8227-857b6df48b5d', ['publicRelationTheorem10Name', 'publicRelationTheorem10Description']],
  ['fe831dae-4c58-5784-a93d-ef10a17660ca', ['publicRelationTheorem11Name', 'publicRelationTheorem11Description']],
  ['0119ab46-9188-5fb1-bd2d-a832089a2d2f', ['publicRelationTheorem12Name', 'publicRelationTheorem12Description']],
  ['25f5e786-e813-5234-aa62-dcbdebf6848f', ['publicRelationTheorem13Name', 'publicRelationTheorem13Description']],
  ['018d8e2a-c5f1-5b00-bf2f-89b9703b6c69', ['publicRelationTheorem14Name', 'publicRelationTheorem14Description']],
  ['d4153be4-1c5b-51b3-805f-ab0dd92ae102', ['publicRelationTheorem15Name', 'publicRelationTheorem15Description']],
  ['b8bc784d-852d-59bc-9bda-994edd9b5b75', ['publicRelationTheorem16Name', 'publicRelationTheorem16Description']],
  ['7aa7de4b-0f53-575f-b98e-cc67a962f05b', ['publicRelationTheorem17Name', 'publicRelationTheorem17Description']],
  ['80394553-4fba-5cb5-9a62-dad38e402b78', ['publicRelationTheorem18Name', 'publicRelationTheorem18Description']],
  ['d15fc567-f798-5f6f-967b-9fa8da33e94f', ['publicRelationTheorem19Name', 'publicRelationTheorem19Description']],
  ['910c8249-6c19-56ab-8439-d84142fd80d9', ['publicRelationTheorem20Name', 'publicRelationTheorem20Description']],
  ['84ccacac-f27d-54c3-b5d8-459dc44ad4fb', ['publicRelationTheorem21Name', 'publicRelationTheorem21Description']],
  ['a627fa32-6c96-5b0c-884d-df5713b4adfc', ['publicRelationTheorem22Name', 'publicRelationTheorem22Description']],
  ['0ab293d1-c477-5f34-8b2f-993eaebb4bd2', ['publicRelationTheorem23Name', 'publicRelationTheorem23Description']],
  ['df44ce4d-f19e-53c1-8b41-414849b7ca62', ['publicRelationTheorem24Name', 'publicRelationTheorem24Description']],
  ['87075f17-5dcb-5e32-b7b2-4312b18abf84', ['publicRelationTheorem25Name', 'publicRelationTheorem25Description']],
  ['2b75f474-817e-588a-aaab-4d51856b5a98', ['publicRelationTheorem26Name', 'publicRelationTheorem26Description']],
  ['d97033cd-6b20-5124-8300-3f93a0fb73be', ['publicRelationTheorem27Name', 'publicRelationTheorem27Description']],
  ['d2f7270e-4b07-53de-8b8a-71aa11e8d217', ['publicRelationTheorem28Name', 'publicRelationTheorem28Description']],
  ['b5133339-970a-5f98-a0c5-17b38e58f061', ['publicRelationTheorem29Name', 'publicRelationTheorem29Description']],
  ['9065d163-6a00-58a0-a2dc-9b8d462afdcc', ['publicRelationTheorem30Name', 'publicRelationTheorem30Description']],
  ['54a7788b-fc8b-57af-aadb-23f08aad3b8d', ['publicRelationTheorem31Name', 'publicRelationTheorem31Description']],
  ['7a325758-6e21-5186-962e-6b86d97bf543', ['publicRelationTheorem32Name', 'publicRelationTheorem32Description']],
  ['a6d42759-69b2-52c7-80a8-a5c9fe1dc244', ['publicRelationTheorem33Name', 'publicRelationTheorem33Description']],
])

// Public IDs scope this display copy to the published entities.
export function publicSetCopy(publicId: string | undefined) {
  const keys = publicId ? publicSetMessageKeys.get(publicId) : undefined
  return keys && { name: t(keys[0]), description: t(keys[1]) }
}
