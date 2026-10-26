BEGIN TRANSACTION;
CREATE TABLE authoring_provenance (
	entity_kind TEXT NOT NULL,
	entity_id TEXT NOT NULL,
	via TEXT NOT NULL,
	provider TEXT,
	model TEXT,
	user_input TEXT,
	accepted_by TEXT,
	created_at DATETIME NOT NULL,
	CONSTRAINT pk_authoring_provenance PRIMARY KEY (entity_kind, entity_id, created_at)
);
INSERT INTO "authoring_provenance" VALUES('proof','1','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','2','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','3','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','4','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','5','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','6','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('formula','20','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('definition','1','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
CREATE TABLE "axiom" (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	formula_id INTEGER NOT NULL,
	origin_kind TEXT NOT NULL,
	definition_id INTEGER,
	description TEXT,
	remarks TEXT,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	public_id TEXT NOT NULL,
	CONSTRAINT ck_axiom_known_origin_kind CHECK (origin_kind IN ('primitive', 'definition_derived')),
	CONSTRAINT ck_axiom_origin_definition_consistency CHECK ((origin_kind = 'primitive' AND definition_id IS NULL) OR (origin_kind = 'definition_derived' AND definition_id IS NOT NULL)),
	CONSTRAINT fk_axiom_definition_id_definition FOREIGN KEY(definition_id) REFERENCES definition (id) ON DELETE CASCADE,
	CONSTRAINT fk_axiom_formula_id_formula FOREIGN KEY(formula_id) REFERENCES formula (id),
	CONSTRAINT pk_axiom PRIMARY KEY (id),
	CONSTRAINT uq_axiom_definition_id UNIQUE (definition_id),
	CONSTRAINT uq_axiom_name UNIQUE (name),
	CONSTRAINT uq_axiom_public_id UNIQUE (public_id)
);
INSERT INTO "axiom" VALUES(1,'ヒルベルト公理K',1,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','40fd0ee6-c625-560e-b002-db31582fe8ae');
INSERT INTO "axiom" VALUES(2,'ヒルベルト公理S',2,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','f78bf2fa-26c3-5047-ae0d-f90393cd2555');
INSERT INTO "axiom" VALUES(3,'全称除去公理',3,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','5e6cd880-e55e-508c-ae3f-bd2069977882');
INSERT INTO "axiom" VALUES(4,'全称分配公理',4,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','3e665eca-292d-5291-b652-d5eaffb88b9a');
INSERT INTO "axiom" VALUES(5,'等号反射律公理',5,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','8489a563-5ed6-51b0-81dd-dcc43ffbf83f');
INSERT INTO "axiom" VALUES(6,'等号代入公理',6,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','6b768878-ac8e-5c4b-b954-bf8304a0bc2f');
INSERT INTO "axiom" VALUES(7,'定数命題の全称導入公理',7,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','23aa9159-805e-5749-8be2-648523b3c1d5');
INSERT INTO "axiom" VALUES(8,'パース公理',8,'primitive',NULL,NULL,'ヒルベルト体系のシード','2026-10-25 00:00:00.000000','a4169fa3-8198-51f5-9f57-7ea6a09e71b7');
INSERT INTO "axiom" VALUES(9,'同式含意 定義公理',20,'definition_derived',1,NULL,'Self-implication connective: a standard definitional abbreviation.','2026-10-25 00:00:00.000000','7b3246e8-3661-502e-8a47-2b1de0e3e51c');
CREATE TABLE axiom_system (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	remarks TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_axiom_system PRIMARY KEY (id),
	CONSTRAINT uq_axiom_system_name UNIQUE (name)
);
INSERT INTO "axiom_system" VALUES(1,'ヒルベルト体系（コア）','最小限のヒルベルト流コア公理スキーマ。','2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system" VALUES(2,'ヒルベルト体系（古典）','ヒルベルト流コアに古典含意論理を加えた公理系。','2026-10-25 00:00:00.000000');
CREATE TABLE axiom_system_member (
	axiom_system_id INTEGER NOT NULL,
	axiom_id INTEGER NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT fk_axiom_system_member_axiom_id_axiom FOREIGN KEY(axiom_id) REFERENCES axiom (id) ON DELETE CASCADE,
	CONSTRAINT fk_axiom_system_member_axiom_system_id_axiom_system FOREIGN KEY(axiom_system_id) REFERENCES axiom_system (id) ON DELETE CASCADE,
	CONSTRAINT pk_axiom_system_member PRIMARY KEY (axiom_system_id, axiom_id)
);
INSERT INTO "axiom_system_member" VALUES(1,1,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,1,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(1,2,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,2,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(1,3,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,3,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(1,4,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,4,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(1,5,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,5,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(1,6,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,6,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(1,7,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,7,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(2,8,'2026-10-25 00:00:00.000000');
CREATE TABLE axiom_tag (
	axiom_id INTEGER NOT NULL,
	tag_id INTEGER NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT fk_axiom_tag_axiom_id_axiom FOREIGN KEY(axiom_id) REFERENCES axiom (id) ON DELETE CASCADE,
	CONSTRAINT fk_axiom_tag_tag_id_tag FOREIGN KEY(tag_id) REFERENCES tag (id) ON DELETE CASCADE,
	CONSTRAINT pk_axiom_tag PRIMARY KEY (axiom_id, tag_id)
);
CREATE TABLE "definition" (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	kind TEXT NOT NULL,
	new_symbol_id INTEGER NOT NULL,
	requires_existence_proof BOOLEAN DEFAULT 0 NOT NULL,
	requires_uniqueness_proof BOOLEAN DEFAULT 0 NOT NULL,
	existence_uniqueness_proof_id INTEGER,
	display_formula_id INTEGER,
	description TEXT,
	remarks TEXT,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	public_id TEXT NOT NULL,
	CONSTRAINT ck_definition_function_desc_requires_proof CHECK ((kind = 'function_desc' AND existence_uniqueness_proof_id IS NOT NULL) OR (kind <> 'function_desc' AND existence_uniqueness_proof_id IS NULL)),
	CONSTRAINT ck_definition_known_kind CHECK (kind IN ('predicate', 'function', 'logical', 'quant_prop', 'quant_term', 'function_desc')),
	CONSTRAINT fk_definition_display_formula_id_formula FOREIGN KEY(display_formula_id) REFERENCES formula (id),
	CONSTRAINT fk_definition_existence_uniqueness_proof_id_proof FOREIGN KEY(existence_uniqueness_proof_id) REFERENCES proof (id),
	CONSTRAINT fk_definition_new_symbol_id_symbol FOREIGN KEY(new_symbol_id) REFERENCES symbol (id),
	CONSTRAINT pk_definition PRIMARY KEY (id),
	CONSTRAINT uq_definition_name UNIQUE (name),
	CONSTRAINT uq_definition_new_symbol_id UNIQUE (new_symbol_id),
	CONSTRAINT uq_definition_public_id UNIQUE (public_id)
);
INSERT INTO "definition" VALUES(1,'同式含意','logical',18,0,0,NULL,NULL,NULL,'Self-implication connective: a standard definitional abbreviation.','2026-10-25 00:00:00.000000','84530e23-b296-594f-9e95-4770e23a52a5');
CREATE TABLE definition_formal_param (
	definition_id INTEGER NOT NULL,
	ord INTEGER NOT NULL,
	param_symbol_id INTEGER NOT NULL,
	CONSTRAINT ck_definition_formal_param_ord_nonnegative CHECK (ord >= 0),
	CONSTRAINT fk_definition_formal_param_definition_id_definition FOREIGN KEY(definition_id) REFERENCES definition (id) ON DELETE CASCADE,
	CONSTRAINT fk_definition_formal_param_param_symbol_id_symbol FOREIGN KEY(param_symbol_id) REFERENCES symbol (id),
	CONSTRAINT pk_definition_formal_param PRIMARY KEY (definition_id, ord)
);
INSERT INTO "definition_formal_param" VALUES(1,0,10);
CREATE TABLE definition_tag (
	definition_id INTEGER NOT NULL,
	tag_id INTEGER NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT fk_definition_tag_definition_id_definition FOREIGN KEY(definition_id) REFERENCES definition (id) ON DELETE CASCADE,
	CONSTRAINT fk_definition_tag_tag_id_tag FOREIGN KEY(tag_id) REFERENCES tag (id) ON DELETE CASCADE,
	CONSTRAINT pk_definition_tag PRIMARY KEY (definition_id, tag_id)
);
CREATE TABLE "formula" (
	id INTEGER NOT NULL,
	formula_type_id INTEGER NOT NULL,
	hash TEXT NOT NULL,
	token_count INTEGER NOT NULL,
	description TEXT,
	remarks TEXT,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	public_id TEXT NOT NULL,
	CONSTRAINT ck_formula_token_count_positive CHECK (token_count > 0),
	CONSTRAINT fk_formula_formula_type_id_formula_type FOREIGN KEY(formula_type_id) REFERENCES formula_type (id),
	CONSTRAINT pk_formula PRIMARY KEY (id),
	CONSTRAINT uq_formula_hash UNIQUE (hash),
	CONSTRAINT uq_formula_public_id UNIQUE (public_id)
);
INSERT INTO "formula" VALUES(1,2,'b69e1f967d1dfde9d6930a6c1cd1a689a433d2d9faec9a08a97da2c32b4f1788',5,NULL,'ヒルベルト公理Kの論理式','2026-10-25 00:00:00.000000','34975be9-5daa-5c05-81e3-bc715764b466');
INSERT INTO "formula" VALUES(2,2,'f5f4c44a0c4d860f9359f083d81cc1abf9fccc1363b29955ba58a46c56e20770',13,NULL,'ヒルベルト公理Sの論理式','2026-10-25 00:00:00.000000','8dcb6e1b-0510-5657-ba18-e8a22a7f8b88');
INSERT INTO "formula" VALUES(3,2,'f6630dccd1deaafb61d3c2941b82e063750dbb8c0d6a649c49d4e4c08762e8ea',6,NULL,'全称除去公理の論理式','2026-10-25 00:00:00.000000','c63bee19-55d5-5a83-917a-bfcd962df657');
INSERT INTO "formula" VALUES(4,2,'8cefde862c95c198f942ac726a533c2f67d6fbafcdc647ed15907411e0361bb3',14,NULL,'全称分配公理の論理式','2026-10-25 00:00:00.000000','7cbe181b-ba2f-560d-aaba-4f22b25d167a');
INSERT INTO "formula" VALUES(5,2,'3e90d11e1bfcd4e7ecd494bb05a06d0ecc6b63e51651d547afe2920d4c1997f7',3,NULL,'等号反射律公理の論理式','2026-10-25 00:00:00.000000','6b1dc303-a6e7-51d5-99d4-50fdfa8f0391');
INSERT INTO "formula" VALUES(6,2,'c24c180eb08243e43a79c75b07c3edbb7de7d6b7cfdf79ecd5710a0684186bff',9,NULL,'等号代入公理の論理式','2026-10-25 00:00:00.000000','d15ead78-1e74-5418-9cb2-dc674812870f');
INSERT INTO "formula" VALUES(7,2,'f74dffbd711790e07b044f1d9046918ae7ff0075d20dec3f6c3b4964d707cf15',4,NULL,'定数命題の全称導入公理の論理式','2026-10-25 00:00:00.000000','998a72b3-e7af-5c9a-a1f9-1003bfca3d27');
INSERT INTO "formula" VALUES(8,2,'32b85f6afcb4264d7a68230b08619714df1517c63370421aaecd05019746d248',7,NULL,'パース公理の論理式','2026-10-25 00:00:00.000000','059b4bd7-c8cd-5c09-b573-b65359032f1f');
INSERT INTO "formula" VALUES(9,2,'ea9c32ccb6929a3a2d9dbdf1917b0074d3e020d6f1f401bae0d05929e112614f',3,NULL,NULL,'2026-10-25 00:00:00.000000','df0e089f-6122-5b40-aa60-f49b12a3082f');
INSERT INTO "formula" VALUES(10,2,'197b6b086ab94deddaa3b8c6f3e680e37c7b5ce2ccef525f802bd76fa8a8e01f',1,NULL,NULL,'2026-10-25 00:00:00.000000','4c4799ef-cd56-5649-8fbf-51d3a45ec57f');
INSERT INTO "formula" VALUES(11,2,'0f7cdbe4c13231f39c47e59fbdacbab7a312535c2defbbe629bf66459e4ce0f1',7,NULL,NULL,'2026-10-25 00:00:00.000000','612c0f9b-4830-519b-8405-1a403308d714');
INSERT INTO "formula" VALUES(12,2,'0a7da5e468a72d02711987d6f18e01cf2a34c80dd10fc5746d07f6fe1c975059',5,NULL,NULL,'2026-10-25 00:00:00.000000','ce583c30-4b1c-5149-9d59-7ac4758f67e1');
INSERT INTO "formula" VALUES(13,2,'18e737797d6931d7a9c8adebf79a9bd7abd2e8ac56fa86173e9af007256a7ea3',17,NULL,NULL,'2026-10-25 00:00:00.000000','a3929295-782e-5e8f-82c8-68843420ec80');
INSERT INTO "formula" VALUES(14,2,'5bb2f2786240d81f6b5cebc83d46036ff9ca9726ecdfb4a4845a7666371aa224',9,NULL,NULL,'2026-10-25 00:00:00.000000','179993a8-7c3a-57e3-82e4-2e6587a0a241');
INSERT INTO "formula" VALUES(15,2,'65460d2c536a25467937bd7928fc6fc7f3a6b0b99ac36d523b05329ff2efa0cc',1,NULL,NULL,'2026-10-25 00:00:00.000000','793b37e6-402a-596e-94f5-2b323c342ec2');
INSERT INTO "formula" VALUES(16,2,'d162ddb918fe947888e69d32af1ccedf14e77eb541ba34b9fc4dee456ab9ba8a',3,NULL,NULL,'2026-10-25 00:00:00.000000','ba2cc4ad-fe1f-5e1a-9096-57c75ab2113d');
INSERT INTO "formula" VALUES(17,2,'a93326f20242f2a3a0efbc8fa905aea8f8fc16e6253ec1cbe5b1c88cd68070bf',3,NULL,NULL,'2026-10-25 00:00:00.000000','c12f300d-21d4-53c1-bc9a-56705593a891');
INSERT INTO "formula" VALUES(18,2,'b1b95f7e3a75fc9018e4453b6c7f5ce3702548d26c9c29cc13d686995f99ef51',1,NULL,NULL,'2026-10-25 00:00:00.000000','e56b8d0d-75f2-5ff5-854d-04c631b343c8');
INSERT INTO "formula" VALUES(19,2,'195e9ed9896ea4c982ce062073847d748ac82ef02e3d0474b7bc1e3b9894ca9f',3,NULL,NULL,'2026-10-25 00:00:00.000000','e3162cb8-7c58-50d9-b893-5ce6352bdfc8');
INSERT INTO "formula" VALUES(20,2,'5aca1d5d157fdb68eb0655c7ac60c1fbae22620188e6a2b1c5ad4f47e52f7123',6,NULL,'同式含意 の定義公理式','2026-10-25 00:00:00.000000','dd307a8b-18a1-5b91-90fa-b18c15bcf188');
CREATE TABLE formula_token (
	id INTEGER NOT NULL,
	formula_id INTEGER NOT NULL,
	position INTEGER NOT NULL,
	symbol_id INTEGER,
	de_bruijn_index INTEGER,
	CONSTRAINT ck_formula_token_exactly_one_kind CHECK ((symbol_id IS NOT NULL AND de_bruijn_index IS NULL) OR (symbol_id IS NULL AND de_bruijn_index IS NOT NULL AND de_bruijn_index >= 0)),
	CONSTRAINT ck_formula_token_position_nonnegative CHECK (position >= 0),
	CONSTRAINT fk_formula_token_formula_id_formula FOREIGN KEY(formula_id) REFERENCES formula (id) ON DELETE CASCADE,
	CONSTRAINT fk_formula_token_symbol_id_symbol FOREIGN KEY(symbol_id) REFERENCES symbol (id),
	CONSTRAINT pk_formula_token PRIMARY KEY (id),
	CONSTRAINT uq_formula_token_formula_id UNIQUE (formula_id, position)
);
INSERT INTO "formula_token" VALUES(1,1,0,5,NULL);
INSERT INTO "formula_token" VALUES(2,1,1,10,NULL);
INSERT INTO "formula_token" VALUES(3,1,2,5,NULL);
INSERT INTO "formula_token" VALUES(4,1,3,11,NULL);
INSERT INTO "formula_token" VALUES(5,1,4,10,NULL);
INSERT INTO "formula_token" VALUES(6,2,0,5,NULL);
INSERT INTO "formula_token" VALUES(7,2,1,5,NULL);
INSERT INTO "formula_token" VALUES(8,2,2,10,NULL);
INSERT INTO "formula_token" VALUES(9,2,3,5,NULL);
INSERT INTO "formula_token" VALUES(10,2,4,11,NULL);
INSERT INTO "formula_token" VALUES(11,2,5,12,NULL);
INSERT INTO "formula_token" VALUES(12,2,6,5,NULL);
INSERT INTO "formula_token" VALUES(13,2,7,5,NULL);
INSERT INTO "formula_token" VALUES(14,2,8,10,NULL);
INSERT INTO "formula_token" VALUES(15,2,9,11,NULL);
INSERT INTO "formula_token" VALUES(16,2,10,5,NULL);
INSERT INTO "formula_token" VALUES(17,2,11,10,NULL);
INSERT INTO "formula_token" VALUES(18,2,12,12,NULL);
INSERT INTO "formula_token" VALUES(19,3,0,5,NULL);
INSERT INTO "formula_token" VALUES(20,3,1,7,NULL);
INSERT INTO "formula_token" VALUES(21,3,2,13,NULL);
INSERT INTO "formula_token" VALUES(22,3,3,NULL,0);
INSERT INTO "formula_token" VALUES(23,3,4,13,NULL);
INSERT INTO "formula_token" VALUES(24,3,5,17,NULL);
INSERT INTO "formula_token" VALUES(25,4,0,5,NULL);
INSERT INTO "formula_token" VALUES(26,4,1,7,NULL);
INSERT INTO "formula_token" VALUES(27,4,2,5,NULL);
INSERT INTO "formula_token" VALUES(28,4,3,13,NULL);
INSERT INTO "formula_token" VALUES(29,4,4,NULL,0);
INSERT INTO "formula_token" VALUES(30,4,5,14,NULL);
INSERT INTO "formula_token" VALUES(31,4,6,NULL,0);
INSERT INTO "formula_token" VALUES(32,4,7,5,NULL);
INSERT INTO "formula_token" VALUES(33,4,8,7,NULL);
INSERT INTO "formula_token" VALUES(34,4,9,13,NULL);
INSERT INTO "formula_token" VALUES(35,4,10,NULL,0);
INSERT INTO "formula_token" VALUES(36,4,11,7,NULL);
INSERT INTO "formula_token" VALUES(37,4,12,14,NULL);
INSERT INTO "formula_token" VALUES(38,4,13,NULL,0);
INSERT INTO "formula_token" VALUES(39,5,0,9,NULL);
INSERT INTO "formula_token" VALUES(40,5,1,15,NULL);
INSERT INTO "formula_token" VALUES(41,5,2,15,NULL);
INSERT INTO "formula_token" VALUES(42,6,0,5,NULL);
INSERT INTO "formula_token" VALUES(43,6,1,9,NULL);
INSERT INTO "formula_token" VALUES(44,6,2,15,NULL);
INSERT INTO "formula_token" VALUES(45,6,3,16,NULL);
INSERT INTO "formula_token" VALUES(46,6,4,5,NULL);
INSERT INTO "formula_token" VALUES(47,6,5,13,NULL);
INSERT INTO "formula_token" VALUES(48,6,6,15,NULL);
INSERT INTO "formula_token" VALUES(49,6,7,13,NULL);
INSERT INTO "formula_token" VALUES(50,6,8,16,NULL);
INSERT INTO "formula_token" VALUES(51,7,0,5,NULL);
INSERT INTO "formula_token" VALUES(52,7,1,10,NULL);
INSERT INTO "formula_token" VALUES(53,7,2,7,NULL);
INSERT INTO "formula_token" VALUES(54,7,3,10,NULL);
INSERT INTO "formula_token" VALUES(55,8,0,5,NULL);
INSERT INTO "formula_token" VALUES(56,8,1,5,NULL);
INSERT INTO "formula_token" VALUES(57,8,2,5,NULL);
INSERT INTO "formula_token" VALUES(58,8,3,10,NULL);
INSERT INTO "formula_token" VALUES(59,8,4,11,NULL);
INSERT INTO "formula_token" VALUES(60,8,5,10,NULL);
INSERT INTO "formula_token" VALUES(61,8,6,10,NULL);
INSERT INTO "formula_token" VALUES(62,9,0,5,NULL);
INSERT INTO "formula_token" VALUES(63,9,1,10,NULL);
INSERT INTO "formula_token" VALUES(64,9,2,10,NULL);
INSERT INTO "formula_token" VALUES(65,10,0,10,NULL);
INSERT INTO "formula_token" VALUES(66,11,0,5,NULL);
INSERT INTO "formula_token" VALUES(67,11,1,10,NULL);
INSERT INTO "formula_token" VALUES(68,11,2,5,NULL);
INSERT INTO "formula_token" VALUES(69,11,3,5,NULL);
INSERT INTO "formula_token" VALUES(70,11,4,10,NULL);
INSERT INTO "formula_token" VALUES(71,11,5,10,NULL);
INSERT INTO "formula_token" VALUES(72,11,6,10,NULL);
INSERT INTO "formula_token" VALUES(73,12,0,5,NULL);
INSERT INTO "formula_token" VALUES(74,12,1,10,NULL);
INSERT INTO "formula_token" VALUES(75,12,2,5,NULL);
INSERT INTO "formula_token" VALUES(76,12,3,10,NULL);
INSERT INTO "formula_token" VALUES(77,12,4,10,NULL);
INSERT INTO "formula_token" VALUES(78,13,0,5,NULL);
INSERT INTO "formula_token" VALUES(79,13,1,5,NULL);
INSERT INTO "formula_token" VALUES(80,13,2,10,NULL);
INSERT INTO "formula_token" VALUES(81,13,3,5,NULL);
INSERT INTO "formula_token" VALUES(82,13,4,5,NULL);
INSERT INTO "formula_token" VALUES(83,13,5,10,NULL);
INSERT INTO "formula_token" VALUES(84,13,6,10,NULL);
INSERT INTO "formula_token" VALUES(85,13,7,10,NULL);
INSERT INTO "formula_token" VALUES(86,13,8,5,NULL);
INSERT INTO "formula_token" VALUES(87,13,9,5,NULL);
INSERT INTO "formula_token" VALUES(88,13,10,10,NULL);
INSERT INTO "formula_token" VALUES(89,13,11,5,NULL);
INSERT INTO "formula_token" VALUES(90,13,12,10,NULL);
INSERT INTO "formula_token" VALUES(91,13,13,10,NULL);
INSERT INTO "formula_token" VALUES(92,13,14,5,NULL);
INSERT INTO "formula_token" VALUES(93,13,15,10,NULL);
INSERT INTO "formula_token" VALUES(94,13,16,10,NULL);
INSERT INTO "formula_token" VALUES(95,14,0,5,NULL);
INSERT INTO "formula_token" VALUES(96,14,1,5,NULL);
INSERT INTO "formula_token" VALUES(97,14,2,10,NULL);
INSERT INTO "formula_token" VALUES(98,14,3,5,NULL);
INSERT INTO "formula_token" VALUES(99,14,4,10,NULL);
INSERT INTO "formula_token" VALUES(100,14,5,10,NULL);
INSERT INTO "formula_token" VALUES(101,14,6,5,NULL);
INSERT INTO "formula_token" VALUES(102,14,7,10,NULL);
INSERT INTO "formula_token" VALUES(103,14,8,10,NULL);
INSERT INTO "formula_token" VALUES(104,15,0,12,NULL);
INSERT INTO "formula_token" VALUES(105,16,0,5,NULL);
INSERT INTO "formula_token" VALUES(106,16,1,10,NULL);
INSERT INTO "formula_token" VALUES(107,16,2,11,NULL);
INSERT INTO "formula_token" VALUES(108,17,0,5,NULL);
INSERT INTO "formula_token" VALUES(109,17,1,11,NULL);
INSERT INTO "formula_token" VALUES(110,17,2,12,NULL);
INSERT INTO "formula_token" VALUES(111,18,0,11,NULL);
INSERT INTO "formula_token" VALUES(112,19,0,5,NULL);
INSERT INTO "formula_token" VALUES(113,19,1,11,NULL);
INSERT INTO "formula_token" VALUES(114,19,2,10,NULL);
INSERT INTO "formula_token" VALUES(115,20,0,6,NULL);
INSERT INTO "formula_token" VALUES(116,20,1,18,NULL);
INSERT INTO "formula_token" VALUES(117,20,2,10,NULL);
INSERT INTO "formula_token" VALUES(118,20,3,5,NULL);
INSERT INTO "formula_token" VALUES(119,20,4,10,NULL);
INSERT INTO "formula_token" VALUES(120,20,5,10,NULL);
CREATE TABLE formula_type (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	remarks TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_formula_type PRIMARY KEY (id),
	CONSTRAINT uq_formula_type_name UNIQUE (name)
);
INSERT INTO "formula_type" VALUES(1,'項','term. 数学的な実体を表す論理式。','2026-10-25 00:00:00.000000');
INSERT INTO "formula_type" VALUES(2,'命題','proposition. 真偽を問える論理式。','2026-10-25 00:00:00.000000');
CREATE TABLE inference_rule (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	kind TEXT NOT NULL,
	tier TEXT NOT NULL,
	elimination_procedure TEXT,
	premise_count INTEGER NOT NULL,
	requires_variable_param BOOLEAN DEFAULT 0 NOT NULL,
	remarks TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT ck_inference_rule_admissible_requires_elimination_procedure CHECK ((tier = 'admissible') = (elimination_procedure IS NOT NULL)),
	CONSTRAINT ck_inference_rule_known_kind CHECK (kind IN ('modus_ponens', 'generalization', 'implication_intro')),
	CONSTRAINT ck_inference_rule_known_tier CHECK (tier IN ('primitive', 'derived', 'admissible', 'recognizer')),
	CONSTRAINT ck_inference_rule_premise_count_nonnegative CHECK (premise_count >= 0),
	CONSTRAINT pk_inference_rule PRIMARY KEY (id),
	CONSTRAINT uq_inference_rule_name UNIQUE (name)
);
INSERT INTO "inference_rule" VALUES(1,'MP','modus_ponens','primitive',NULL,2,0,'φ と φ→ψ から ψ を導く','2026-10-25 00:00:00.000000');
INSERT INTO "inference_rule" VALUES(2,'Gen','generalization','primitive',NULL,1,1,'φ から ∀°x.φ を導く','2026-10-25 00:00:00.000000');
INSERT INTO "inference_rule" VALUES(3,'ImpIntro','implication_intro','admissible','expand_implication_intro',1,0,'仮定 φ の下での ψ から φ→ψ を導き、その仮定を落とす (Tier 2 許容規則。除去手続きは expand_implication_intro、設計書 §9.3)','2026-10-25 00:00:00.000000');
CREATE TABLE namespace (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	parent_id INTEGER,
	CONSTRAINT fk_namespace_parent_id_namespace FOREIGN KEY(parent_id) REFERENCES namespace (id),
	CONSTRAINT pk_namespace PRIMARY KEY (id),
	CONSTRAINT uq_namespace_name UNIQUE (name)
);
INSERT INTO "namespace" VALUES(1,'dem.foundation',NULL);
INSERT INTO "namespace" VALUES(2,'dem.foundation.logic',1);
CREATE TABLE "proof" (
	id INTEGER NOT NULL,
	theorem_id INTEGER NOT NULL,
	name TEXT,
	status TEXT NOT NULL,
	remarks TEXT,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	public_id TEXT NOT NULL,
	identity_ordinal INTEGER NOT NULL,
	CONSTRAINT ck_proof_known_status CHECK (status IN ('draft', 'verified', 'rejected')),
	CONSTRAINT fk_proof_theorem_id_theorem FOREIGN KEY(theorem_id) REFERENCES theorem (id),
	CONSTRAINT pk_proof PRIMARY KEY (id),
	CONSTRAINT uq_proof_public_id UNIQUE (public_id),
	CONSTRAINT uq_proof_theorem_identity_ordinal UNIQUE (theorem_id, identity_ordinal)
);
INSERT INTO "proof" VALUES(1,1,'KとSによる証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','1f0c36bb-6f2f-550d-82b1-5dd3dfb4ad4a',0);
INSERT INTO "proof" VALUES(2,1,'含意導入による証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','825a0467-eb8a-5d12-9624-7ec629863540',1);
INSERT INTO "proof" VALUES(3,2,'連続したMP','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','95c140f0-8579-51b5-a68a-b1b44bafbf55',0);
INSERT INTO "proof" VALUES(4,3,'既存の導出の引用','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','d5f33408-0a1c-53ac-9f4e-290a07911480',0);
INSERT INTO "proof" VALUES(5,4,'古典公理の使用','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','02ad6140-f683-5235-9dd3-4247d3f682da',0);
INSERT INTO "proof" VALUES(6,5,'Kによる前提の保持','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','19e9ee08-d8b1-526f-b96e-b22f41c2c2d1',0);
CREATE TABLE proof_identity_sequence (
	theorem_id INTEGER NOT NULL,
	next_ordinal INTEGER NOT NULL,
	CONSTRAINT fk_proof_identity_sequence_theorem_id_theorem FOREIGN KEY(theorem_id) REFERENCES theorem (id) ON DELETE CASCADE,
	CONSTRAINT pk_proof_identity_sequence PRIMARY KEY (theorem_id)
);
INSERT INTO "proof_identity_sequence" VALUES(1,2);
INSERT INTO "proof_identity_sequence" VALUES(2,1);
INSERT INTO "proof_identity_sequence" VALUES(3,1);
INSERT INTO "proof_identity_sequence" VALUES(4,1);
INSERT INTO "proof_identity_sequence" VALUES(5,1);
CREATE TABLE proof_step (
	proof_id INTEGER NOT NULL,
	ord INTEGER NOT NULL,
	step_kind TEXT NOT NULL,
	conclusion_formula_id INTEGER NOT NULL,
	premise_ord INTEGER,
	axiom_id INTEGER,
	applied_proof_id INTEGER,
	inference_rule_id INTEGER,
	gen_variable_symbol_id INTEGER,
	remarks TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT ck_proof_step_gen_variable_only_for_rule CHECK (step_kind = 'rule' OR gen_variable_symbol_id IS NULL),
	CONSTRAINT ck_proof_step_kind_column_consistency CHECK ((step_kind = 'premise' AND premise_ord IS NOT NULL AND axiom_id IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'assumption' AND premise_ord IS NULL AND axiom_id IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'axiom' AND axiom_id IS NOT NULL AND premise_ord IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'theorem' AND applied_proof_id IS NOT NULL AND premise_ord IS NULL AND axiom_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'rule' AND inference_rule_id IS NOT NULL AND premise_ord IS NULL AND axiom_id IS NULL AND applied_proof_id IS NULL)),
	CONSTRAINT ck_proof_step_known_step_kind CHECK (step_kind IN ('premise', 'assumption', 'axiom', 'theorem', 'rule')),
	CONSTRAINT ck_proof_step_ord_nonnegative CHECK (ord >= 0),
	CONSTRAINT fk_proof_step_applied_proof_id_proof FOREIGN KEY(applied_proof_id) REFERENCES proof (id),
	CONSTRAINT fk_proof_step_axiom_id_axiom FOREIGN KEY(axiom_id) REFERENCES axiom (id),
	CONSTRAINT fk_proof_step_conclusion_formula_id_formula FOREIGN KEY(conclusion_formula_id) REFERENCES formula (id),
	CONSTRAINT fk_proof_step_gen_variable_symbol_id_symbol FOREIGN KEY(gen_variable_symbol_id) REFERENCES symbol (id),
	CONSTRAINT fk_proof_step_inference_rule_id_inference_rule FOREIGN KEY(inference_rule_id) REFERENCES inference_rule (id),
	CONSTRAINT fk_proof_step_proof_id_proof FOREIGN KEY(proof_id) REFERENCES proof (id) ON DELETE CASCADE,
	CONSTRAINT pk_proof_step PRIMARY KEY (proof_id, ord)
);
INSERT INTO "proof_step" VALUES(1,0,'axiom',11,NULL,1,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(1,1,'axiom',12,NULL,1,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(1,2,'axiom',13,NULL,2,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(1,3,'rule',14,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(1,4,'rule',9,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(2,0,'assumption',10,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(2,1,'rule',9,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(3,0,'premise',16,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(3,1,'premise',17,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(3,2,'premise',10,2,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(3,3,'rule',18,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(3,4,'rule',15,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(4,0,'premise',16,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(4,1,'premise',17,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(4,2,'premise',10,2,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(4,3,'theorem',15,NULL,NULL,3,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(5,0,'axiom',8,NULL,8,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(6,0,'premise',10,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(6,1,'axiom',1,NULL,1,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(6,2,'rule',19,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
CREATE TABLE proof_step_arg (
	proof_id INTEGER NOT NULL,
	step_ord INTEGER NOT NULL,
	arg_ord INTEGER NOT NULL,
	referenced_step_ord INTEGER NOT NULL,
	CONSTRAINT ck_proof_step_arg_arg_ord_nonnegative CHECK (arg_ord >= 0),
	CONSTRAINT ck_proof_step_arg_references_prior_step CHECK (referenced_step_ord < step_ord),
	CONSTRAINT fk_proof_step_arg_referenced_step FOREIGN KEY(proof_id, referenced_step_ord) REFERENCES proof_step (proof_id, ord),
	CONSTRAINT fk_proof_step_arg_step FOREIGN KEY(proof_id, step_ord) REFERENCES proof_step (proof_id, ord) ON DELETE CASCADE,
	CONSTRAINT pk_proof_step_arg PRIMARY KEY (proof_id, step_ord, arg_ord)
);
INSERT INTO "proof_step_arg" VALUES(1,3,0,0);
INSERT INTO "proof_step_arg" VALUES(1,3,1,2);
INSERT INTO "proof_step_arg" VALUES(1,4,0,1);
INSERT INTO "proof_step_arg" VALUES(1,4,1,3);
INSERT INTO "proof_step_arg" VALUES(2,1,0,0);
INSERT INTO "proof_step_arg" VALUES(2,1,1,0);
INSERT INTO "proof_step_arg" VALUES(3,3,0,2);
INSERT INTO "proof_step_arg" VALUES(3,3,1,0);
INSERT INTO "proof_step_arg" VALUES(3,4,0,3);
INSERT INTO "proof_step_arg" VALUES(3,4,1,1);
INSERT INTO "proof_step_arg" VALUES(4,3,0,0);
INSERT INTO "proof_step_arg" VALUES(4,3,1,1);
INSERT INTO "proof_step_arg" VALUES(4,3,2,2);
INSERT INTO "proof_step_arg" VALUES(6,2,0,0);
INSERT INTO "proof_step_arg" VALUES(6,2,1,1);
CREATE TABLE proof_step_subst_prop (
	proof_id INTEGER NOT NULL,
	step_ord INTEGER NOT NULL,
	source_symbol_id INTEGER NOT NULL,
	body_formula_id INTEGER NOT NULL,
	CONSTRAINT fk_proof_step_subst_prop_body_formula_id_formula FOREIGN KEY(body_formula_id) REFERENCES formula (id),
	CONSTRAINT fk_proof_step_subst_prop_proof_id_proof_step FOREIGN KEY(proof_id, step_ord) REFERENCES proof_step (proof_id, ord) ON DELETE CASCADE,
	CONSTRAINT fk_proof_step_subst_prop_source_symbol_id_symbol FOREIGN KEY(source_symbol_id) REFERENCES symbol (id),
	CONSTRAINT pk_proof_step_subst_prop PRIMARY KEY (proof_id, step_ord, source_symbol_id)
);
INSERT INTO "proof_step_subst_prop" VALUES(1,0,10,10);
INSERT INTO "proof_step_subst_prop" VALUES(1,0,11,9);
INSERT INTO "proof_step_subst_prop" VALUES(1,1,10,10);
INSERT INTO "proof_step_subst_prop" VALUES(1,1,11,10);
INSERT INTO "proof_step_subst_prop" VALUES(1,2,10,10);
INSERT INTO "proof_step_subst_prop" VALUES(1,2,11,9);
INSERT INTO "proof_step_subst_prop" VALUES(1,2,12,10);
INSERT INTO "proof_step_subst_prop" VALUES(6,1,10,10);
INSERT INTO "proof_step_subst_prop" VALUES(6,1,11,18);
CREATE TABLE proof_step_subst_prop_param (
	proof_id INTEGER NOT NULL,
	step_ord INTEGER NOT NULL,
	source_symbol_id INTEGER NOT NULL,
	ord INTEGER NOT NULL,
	formal_param_symbol_id INTEGER NOT NULL,
	CONSTRAINT ck_proof_step_subst_prop_param_ord_nonnegative CHECK (ord >= 0),
	CONSTRAINT fk_proof_step_subst_prop_param_formal_param_symbol_id_symbol FOREIGN KEY(formal_param_symbol_id) REFERENCES symbol (id),
	CONSTRAINT fk_proof_step_subst_prop_param_proof_id_proof_step_subst_prop FOREIGN KEY(proof_id, step_ord, source_symbol_id) REFERENCES proof_step_subst_prop (proof_id, step_ord, source_symbol_id) ON DELETE CASCADE,
	CONSTRAINT pk_proof_step_subst_prop_param PRIMARY KEY (proof_id, step_ord, source_symbol_id, ord)
);
CREATE TABLE proof_step_subst_term (
	proof_id INTEGER NOT NULL,
	step_ord INTEGER NOT NULL,
	source_symbol_id INTEGER NOT NULL,
	target_formula_id INTEGER NOT NULL,
	CONSTRAINT fk_proof_step_subst_term_proof_id_proof_step FOREIGN KEY(proof_id, step_ord) REFERENCES proof_step (proof_id, ord) ON DELETE CASCADE,
	CONSTRAINT fk_proof_step_subst_term_source_symbol_id_symbol FOREIGN KEY(source_symbol_id) REFERENCES symbol (id),
	CONSTRAINT fk_proof_step_subst_term_target_formula_id_formula FOREIGN KEY(target_formula_id) REFERENCES formula (id),
	CONSTRAINT pk_proof_step_subst_term PRIMARY KEY (proof_id, step_ord, source_symbol_id)
);
CREATE TABLE "symbol" (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	symbol_type_id INTEGER NOT NULL,
	arity INTEGER NOT NULL,
	is_primitive BOOLEAN DEFAULT 0 NOT NULL,
	namespace_id INTEGER NOT NULL,
	notation_kind TEXT DEFAULT 'prefix' NOT NULL,
	precedence INTEGER,
	latex_template TEXT,
	remarks TEXT,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	usage_count INTEGER DEFAULT 0 NOT NULL,
	public_id TEXT NOT NULL,
	CONSTRAINT ck_symbol_arity_nonnegative CHECK (arity >= 0),
	CONSTRAINT ck_symbol_infix_requires_arity_two CHECK (notation_kind = 'prefix' OR arity = 2),
	CONSTRAINT ck_symbol_known_notation_kind CHECK (notation_kind IN ('prefix', 'infix')),
	CONSTRAINT ck_symbol_precedence_matches_notation_kind CHECK ((notation_kind = 'infix' AND precedence IS NOT NULL) OR (notation_kind = 'prefix' AND precedence IS NULL)),
	CONSTRAINT fk_symbol_namespace_id_namespace FOREIGN KEY(namespace_id) REFERENCES namespace (id),
	CONSTRAINT fk_symbol_symbol_type_id_symbol_type FOREIGN KEY(symbol_type_id) REFERENCES symbol_type (id),
	CONSTRAINT pk_symbol PRIMARY KEY (id),
	CONSTRAINT uq_symbol_namespace_id UNIQUE (namespace_id, name),
	CONSTRAINT uq_symbol_public_id UNIQUE (public_id)
);
INSERT INTO "symbol" VALUES(1,'⊥',3,0,1,2,'prefix',NULL,'\bot','矛盾','2026-10-25 00:00:00.000000',0,'3200b32b-2960-5ad9-98b0-3c46eea42f9c');
INSERT INTO "symbol" VALUES(2,'¬',3,1,1,2,'prefix',NULL,'\neg','否定','2026-10-25 00:00:00.000000',0,'7ef55380-cb00-59f7-989f-1347cab26b12');
INSERT INTO "symbol" VALUES(3,'∨',3,2,1,2,'infix',30,'\vee','選言','2026-10-25 00:00:00.000000',0,'e9ab484b-d683-5276-987a-af3df5a6e8e9');
INSERT INTO "symbol" VALUES(4,'∧',3,2,1,2,'infix',40,'\wedge','連言','2026-10-25 00:00:00.000000',0,'473e2256-e6c2-5c2a-b45b-7c39f69519e1');
INSERT INTO "symbol" VALUES(5,'→',3,2,1,2,'infix',20,'\implies','含意','2026-10-25 00:00:00.000000',16,'e72831d9-19bc-5094-abd7-359f275f87a1');
INSERT INTO "symbol" VALUES(6,'↔',3,2,1,2,'infix',10,'\iff','同値','2026-10-25 00:00:00.000000',1,'f4243ce5-6563-52e2-ac75-15de5e49cdec');
INSERT INTO "symbol" VALUES(7,'∀',4,1,1,2,'prefix',NULL,'\forall','整形式な項すべてを走る全称量化','2026-10-25 00:00:00.000000',3,'893f7c1c-3e22-564f-a976-0a8e8e241f62');
INSERT INTO "symbol" VALUES(8,'∃',4,1,1,2,'prefix',NULL,'\exists','整形式な項すべてを走る存在量化','2026-10-25 00:00:00.000000',0,'b299df13-8ca1-5327-9b4c-f08b1231a678');
INSERT INTO "symbol" VALUES(9,'=',2,2,1,2,'infix',50,'=','等号','2026-10-25 00:00:00.000000',2,'9c6f5697-7475-52bd-b600-b981e924af62');
INSERT INTO "symbol" VALUES(10,'φ',7,0,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',13,'43c9c73e-69f5-500a-ba17-852af85be0b7');
INSERT INTO "symbol" VALUES(11,'ψ',7,0,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',7,'056bb080-b4a4-5b6c-a651-86b3309dcda6');
INSERT INTO "symbol" VALUES(12,'χ',7,0,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',3,'8e86446f-fb4f-529e-be9c-3ff070066779');
INSERT INTO "symbol" VALUES(13,'φ¹',7,1,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',3,'9cbf22fc-7169-5d86-806b-e21c083d70b1');
INSERT INTO "symbol" VALUES(14,'ψ¹',7,1,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',1,'2efc9d40-a273-5e41-8315-4de58dfabad3');
INSERT INTO "symbol" VALUES(15,'x',6,0,0,2,'prefix',NULL,'x','シード用自由項変数','2026-10-25 00:00:00.000000',2,'58f571b2-5a2d-51ed-8fbf-7e5e6494d147');
INSERT INTO "symbol" VALUES(16,'y',6,0,0,2,'prefix',NULL,'y','シード用自由項変数','2026-10-25 00:00:00.000000',1,'28ffc497-17bf-56b0-b792-3b4f3882539a');
INSERT INTO "symbol" VALUES(17,'t',6,0,0,2,'prefix',NULL,'t','シード用自由項変数','2026-10-25 00:00:00.000000',1,'4b3303de-7abf-5ee7-b37a-4dc01d43665c');
INSERT INTO "symbol" VALUES(18,'同式含意',3,1,0,2,'prefix',NULL,'\mathsf{Self}(#1)','Self-implication connective: a standard definitional abbreviation.','2026-10-25 00:00:00.000000',1,'d807ef85-63f5-5649-aac2-05cc10dda180');
CREATE TABLE symbol_alias (
	id INTEGER NOT NULL,
	symbol_id INTEGER NOT NULL,
	alias TEXT NOT NULL,
	source TEXT NOT NULL,
	CONSTRAINT ck_symbol_alias_known_source CHECK (source IN ('builtin', 'user')),
	CONSTRAINT fk_symbol_alias_symbol_id_symbol FOREIGN KEY(symbol_id) REFERENCES symbol (id) ON DELETE CASCADE,
	CONSTRAINT pk_symbol_alias PRIMARY KEY (id),
	CONSTRAINT uq_symbol_alias_alias UNIQUE (alias)
);
INSERT INTO "symbol_alias" VALUES(1,2,'\neg','builtin');
INSERT INTO "symbol_alias" VALUES(2,2,'!','builtin');
INSERT INTO "symbol_alias" VALUES(3,3,'\vee','builtin');
INSERT INTO "symbol_alias" VALUES(4,3,'\/','builtin');
INSERT INTO "symbol_alias" VALUES(5,4,'\wedge','builtin');
INSERT INTO "symbol_alias" VALUES(6,4,'/\','builtin');
INSERT INTO "symbol_alias" VALUES(7,5,'\to','builtin');
INSERT INTO "symbol_alias" VALUES(8,5,'->','builtin');
INSERT INTO "symbol_alias" VALUES(9,6,'\leftrightarrow','builtin');
INSERT INTO "symbol_alias" VALUES(10,6,'<->','builtin');
INSERT INTO "symbol_alias" VALUES(11,7,'\forall','builtin');
INSERT INTO "symbol_alias" VALUES(12,7,'forall','builtin');
INSERT INTO "symbol_alias" VALUES(13,8,'\exists','builtin');
INSERT INTO "symbol_alias" VALUES(14,8,'exists','builtin');
CREATE TABLE symbol_role (
	role TEXT NOT NULL,
	symbol_id INTEGER NOT NULL,
	remarks TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT ck_symbol_role_known_role CHECK (role IN ('implication', 'universal_quantifier', 'biconditional', 'equality')),
	CONSTRAINT fk_symbol_role_symbol_id_symbol FOREIGN KEY(symbol_id) REFERENCES symbol (id),
	CONSTRAINT pk_symbol_role PRIMARY KEY (role),
	CONSTRAINT uq_symbol_role_symbol_id UNIQUE (symbol_id)
);
INSERT INTO "symbol_role" VALUES('implication',5,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "symbol_role" VALUES('universal_quantifier',7,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "symbol_role" VALUES('biconditional',6,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "symbol_role" VALUES('equality',9,NULL,'2026-10-25 00:00:00.000000');
CREATE TABLE symbol_type (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	output_formula_type_id INTEGER NOT NULL,
	input_formula_type_id INTEGER,
	fixed_arity INTEGER,
	is_quantifier BOOLEAN DEFAULT 0 NOT NULL,
	remarks TEXT,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT ck_symbol_type_fixed_arity_nonnegative CHECK (fixed_arity IS NULL OR fixed_arity >= 0),
	CONSTRAINT ck_symbol_type_input_or_zero_arity CHECK ((input_formula_type_id IS NULL AND fixed_arity = 0) OR (input_formula_type_id IS NOT NULL)),
	CONSTRAINT fk_symbol_type_input_formula_type_id_formula_type FOREIGN KEY(input_formula_type_id) REFERENCES formula_type (id),
	CONSTRAINT fk_symbol_type_output_formula_type_id_formula_type FOREIGN KEY(output_formula_type_id) REFERENCES formula_type (id),
	CONSTRAINT pk_symbol_type PRIMARY KEY (id),
	CONSTRAINT uq_symbol_type_name UNIQUE (name)
);
INSERT INTO "symbol_type" VALUES(1,'関数記号',1,1,NULL,0,'項から項を作る記号','2026-10-25 00:00:00.000000');
INSERT INTO "symbol_type" VALUES(2,'述語記号',2,1,NULL,0,'項から命題を作る記号','2026-10-25 00:00:00.000000');
INSERT INTO "symbol_type" VALUES(3,'論理記号',2,2,NULL,0,'¬, ∨, ∧, →, ↔ など。','2026-10-25 00:00:00.000000');
INSERT INTO "symbol_type" VALUES(4,'命題型量化記号',2,2,1,1,'命題を束縛して命題を作る記号','2026-10-25 00:00:00.000000');
INSERT INTO "symbol_type" VALUES(5,'項型量化記号',1,2,1,1,'項を作る束縛記法。現在インスタンスは無い。','2026-10-25 00:00:00.000000');
INSERT INTO "symbol_type" VALUES(6,'項型自由変数記号',1,NULL,0,0,'自由な項変数','2026-10-25 00:00:00.000000');
INSERT INTO "symbol_type" VALUES(7,'命題型自由変数記号',2,1,NULL,0,'自由な命題変数','2026-10-25 00:00:00.000000');
CREATE TABLE tag (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_tag PRIMARY KEY (id),
	CONSTRAINT uq_tag_name UNIQUE (name)
);
CREATE TABLE "theorem" (
	id INTEGER NOT NULL,
	name TEXT NOT NULL,
	conclusion_formula_id INTEGER NOT NULL,
	status TEXT NOT NULL,
	description TEXT,
	remarks TEXT,
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
	public_id TEXT NOT NULL,
	namespace_id INTEGER NOT NULL,
	CONSTRAINT ck_theorem_known_status CHECK (status IN ('conjecture', 'proven')),
	CONSTRAINT fk_theorem_conclusion_formula_id_formula FOREIGN KEY(conclusion_formula_id) REFERENCES formula (id),
	CONSTRAINT fk_theorem_namespace_id_namespace FOREIGN KEY(namespace_id) REFERENCES namespace (id),
	CONSTRAINT pk_theorem PRIMARY KEY (id),
	CONSTRAINT uq_theorem_namespace_id UNIQUE (namespace_id, name),
	CONSTRAINT uq_theorem_public_id UNIQUE (public_id)
);
INSERT INTO "theorem" VALUES(1,'含意の自己適用',9,'proven','Identity of implication: a direct K/S derivation and an assumption-discharge derivation.',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','04f9430e-2709-5fd3-aaea-d5c792fcea82',2);
INSERT INTO "theorem" VALUES(2,'含意の連鎖',15,'proven','Chaining two implications by modus ponens.',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','1a94c136-668c-58b7-9273-19d552473ae2',2);
INSERT INTO "theorem" VALUES(3,'導出の引用',15,'proven','An explicit dependency edge citing the implication-chain proof.',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','3a20be21-f428-5144-ac5b-ced58a7e9857',2);
INSERT INTO "theorem" VALUES(4,'古典含意の例',8,'proven','Peirce''s schema, valid in the classical Hilbert system only.',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','90b4f2b5-4e6d-5fb3-9343-75070d6c1c2a',2);
INSERT INTO "theorem" VALUES(5,'前提の保持',19,'proven','Retaining a premise through an additional antecedent using K.',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','2377a993-0724-5f88-bf96-7d73e535e47b',2);
CREATE TABLE theorem_premise (
	theorem_id INTEGER NOT NULL,
	ord INTEGER NOT NULL,
	formula_id INTEGER NOT NULL,
	CONSTRAINT ck_theorem_premise_ord_nonnegative CHECK (ord >= 0),
	CONSTRAINT fk_theorem_premise_formula_id_formula FOREIGN KEY(formula_id) REFERENCES formula (id),
	CONSTRAINT fk_theorem_premise_theorem_id_theorem FOREIGN KEY(theorem_id) REFERENCES theorem (id) ON DELETE CASCADE,
	CONSTRAINT pk_theorem_premise PRIMARY KEY (theorem_id, ord)
);
INSERT INTO "theorem_premise" VALUES(2,0,16);
INSERT INTO "theorem_premise" VALUES(2,1,17);
INSERT INTO "theorem_premise" VALUES(2,2,10);
INSERT INTO "theorem_premise" VALUES(3,0,16);
INSERT INTO "theorem_premise" VALUES(3,1,17);
INSERT INTO "theorem_premise" VALUES(3,2,10);
INSERT INTO "theorem_premise" VALUES(5,0,10);
CREATE TABLE theorem_tag (
	theorem_id INTEGER NOT NULL,
	tag_id INTEGER NOT NULL,
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT fk_theorem_tag_tag_id_tag FOREIGN KEY(tag_id) REFERENCES tag (id) ON DELETE CASCADE,
	CONSTRAINT fk_theorem_tag_theorem_id_theorem FOREIGN KEY(theorem_id) REFERENCES theorem (id) ON DELETE CASCADE,
	CONSTRAINT pk_theorem_tag PRIMARY KEY (theorem_id, tag_id)
);
CREATE INDEX ix_formula_token_symbol_formula ON formula_token (symbol_id, formula_id);
COMMIT;
