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
INSERT INTO "authoring_provenance" VALUES('proof','7','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','8','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','9','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','10','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','11','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','12','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','13','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','14','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','15','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','16','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','17','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','18','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','19','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','20','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','21','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','22','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','23','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','24','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','25','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','26','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','27','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "authoring_provenance" VALUES('proof','28','seed',NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
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
INSERT INTO "axiom" VALUES(10,'矛盾除去公理',21,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','dc105544-9958-5c00-838e-a58805f1720e');
INSERT INTO "axiom" VALUES(11,'否定導入公理',22,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','bad16ebf-db51-5354-8dc8-84044f69f407');
INSERT INTO "axiom" VALUES(12,'否定除去公理',23,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','8380701d-7127-518d-b6f4-97519c8a407f');
INSERT INTO "axiom" VALUES(13,'連言導入公理',24,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','fa7363ec-8065-5b36-8383-87dfb95f0410');
INSERT INTO "axiom" VALUES(14,'連言除去公理（左）',25,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','4d0fec14-b78c-58f7-8247-40b1585692aa');
INSERT INTO "axiom" VALUES(15,'連言除去公理（右）',26,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','fa66562b-2a21-5f48-9a84-adafc9902d03');
INSERT INTO "axiom" VALUES(16,'選言導入公理（左）',27,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','c0180c6a-f053-5522-a685-5c834e89b02c');
INSERT INTO "axiom" VALUES(17,'選言導入公理（右）',28,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','fe8021cc-f00c-52e4-a776-7c30dd9e1d44');
INSERT INTO "axiom" VALUES(18,'選言除去公理',29,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','48bda1ee-dc25-5bf7-ae14-374d6a65401e');
INSERT INTO "axiom" VALUES(19,'存在導入公理',30,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','77148fe8-ffd5-553b-9509-a1dde33134d6');
INSERT INTO "axiom" VALUES(20,'存在除去公理',31,'primitive',NULL,'Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。',NULL,'2026-10-25 00:00:00.000000','1f56a039-344f-50f7-afbe-10cf2ecfff06');
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
INSERT INTO "axiom_system" VALUES(3,'直観主義論理','Hilbert coreの量化・等号公理と、結合子・存在量化のスキーマ。パース公理を含まない。','2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system" VALUES(4,'古典論理','Hilbert coreの量化・等号公理と、結合子・存在量化のスキーマ。パース公理を含む。','2026-10-25 00:00:00.000000');
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
INSERT INTO "axiom_system_member" VALUES(3,1,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,2,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,3,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,4,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,5,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,6,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,7,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,10,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,11,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,12,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,13,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,14,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,15,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,16,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,17,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,18,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,19,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(3,20,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,1,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,2,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,3,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,4,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,5,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,6,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,7,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,10,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,11,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,12,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,13,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,14,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,15,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,16,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,17,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,18,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,19,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,20,'2026-10-25 00:00:00.000000');
INSERT INTO "axiom_system_member" VALUES(4,8,'2026-10-25 00:00:00.000000');
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
INSERT INTO "formula" VALUES(21,2,'948c788a35ec3d86c23386f3e58b7938e942c033046b8cff0f55ae55b4c88683',3,NULL,NULL,'2026-10-25 00:00:00.000000','44c1b71b-c364-5eee-a01b-5bf9c91713bd');
INSERT INTO "formula" VALUES(22,2,'c7921f6eecb991a1c945e0617eb4a84701b650e515215f8ce27c6675b51dba36',6,NULL,NULL,'2026-10-25 00:00:00.000000','dcee4502-90ae-5512-bf5e-34ac79eae03b');
INSERT INTO "formula" VALUES(23,2,'6d56fd1e03df7ba1623c05a46a87f7176fba9c348c95d6995407ae4537d576c7',6,NULL,NULL,'2026-10-25 00:00:00.000000','d84f54bb-a27a-53df-a5d0-b637ef51ad15');
INSERT INTO "formula" VALUES(24,2,'a8adaffca88239d96e1c8acb097865aaba044244523d7ac9adca5457afe8afe7',7,NULL,NULL,'2026-10-25 00:00:00.000000','02855e8d-dff7-5b0b-beb8-ff1146ecacf0');
INSERT INTO "formula" VALUES(25,2,'3158054bf6942674732eb5a57e68e4dbb2b643d7ebbde29161dd01ad3852827d',5,NULL,NULL,'2026-10-25 00:00:00.000000','dde00176-0be1-5774-81d1-47b6b7706532');
INSERT INTO "formula" VALUES(26,2,'96aabe8b5c1f04dffbff132517711dca70415605292114e66c8f30e6a059085d',5,NULL,NULL,'2026-10-25 00:00:00.000000','6c9b467f-ad16-5781-b12c-161da88a9c7e');
INSERT INTO "formula" VALUES(27,2,'ea93bee77be22f576fbfe33f12c6cb53f649d6797b1206690bdcc5566c4f9fd0',5,NULL,NULL,'2026-10-25 00:00:00.000000','1a0d8c25-8f1c-5bb3-9502-251f40b86fad');
INSERT INTO "formula" VALUES(28,2,'9acadc02ca26d2c6743bece548ee5c97eb38e2cae0bf48aaa4bba9905d218a06',5,NULL,NULL,'2026-10-25 00:00:00.000000','cc9aef83-c2f6-5473-8664-b4bec4d3e652');
INSERT INTO "formula" VALUES(29,2,'7f3a4f5bccebb4327380f2d54db3e27a609b0a5166d964433ee21990bf36b67b',13,NULL,NULL,'2026-10-25 00:00:00.000000','8e73c551-fa3f-5b0f-a96f-6c80c08f0b09');
INSERT INTO "formula" VALUES(30,2,'e4bf1cfb47c191473dfb02d78ee3a79120cd657a2fd79ef972a805e129c3b64c',6,NULL,NULL,'2026-10-25 00:00:00.000000','94a10f74-b1b9-54a7-a655-c47ba2cdc1ba');
INSERT INTO "formula" VALUES(31,2,'cb113463da9b8a69f44a8e4de9a4bad554585567a185a778d0a7911faa5d05eb',11,NULL,NULL,'2026-10-25 00:00:00.000000','c6716c26-98b4-5a4b-8fe0-0b8d7fc82e90');
INSERT INTO "formula" VALUES(32,2,'ebae4eca39733df25aa7b3586ff8a2a0328c62dfb6f5ece161c5b3c78ac25a9f',1,NULL,NULL,'2026-10-25 00:00:00.000000','1dbd0656-9bdb-5702-ba8b-0e8868f462a3');
INSERT INTO "formula" VALUES(33,2,'78b4231b8daf2922785b518906ce6f591bbb9fd403d172d140295129d085b271',2,NULL,NULL,'2026-10-25 00:00:00.000000','4f4e4d4c-18ae-5f1c-9445-1d7553e2e786');
INSERT INTO "formula" VALUES(34,2,'54590392626faeb13063611a16f2310ae07de6ccd2ec3ff9aca7dcfc0eaf6bc3',3,NULL,NULL,'2026-10-25 00:00:00.000000','38f843d7-f5b9-587d-9a3e-8e253d7748d2');
INSERT INTO "formula" VALUES(35,2,'44069a535d5f528cc963e51ccf4b57f2a47e25e13e44ad41c1ebce1fdcd4b87e',3,NULL,NULL,'2026-10-25 00:00:00.000000','98fbf60f-7211-5d8e-9f56-1afba5a52228');
INSERT INTO "formula" VALUES(36,2,'1b144ce674192b8b5267a9a17616fcfca5e4531777f6f208a86eb787581b7a14',5,NULL,NULL,'2026-10-25 00:00:00.000000','3c2b9e3d-27d0-5a66-8412-f54f1575fa6a');
INSERT INTO "formula" VALUES(37,2,'6be7b2e6fcd0bd59a607d50ead7506ecaecc04eb79b0edeae8bc3f535d660136',3,NULL,NULL,'2026-10-25 00:00:00.000000','d27966f5-6b64-5658-aec4-df4e2534ae30');
INSERT INTO "formula" VALUES(38,2,'cec3be658aa644b828cce93122462bef99893e9785631b42ac09c3666eb04e1d',3,NULL,NULL,'2026-10-25 00:00:00.000000','111ace40-ea54-5561-b33c-e50b30013300');
INSERT INTO "formula" VALUES(39,2,'ca176e020b198ba840c3b54739b1ea69c490561270f4852aa3acc1db9b521171',9,NULL,NULL,'2026-10-25 00:00:00.000000','9e28e537-30b6-52cb-a5b2-d58c4ab4173a');
INSERT INTO "formula" VALUES(40,2,'96dfd7e731969930bc9a23ef13de847b3caf6864b057a8e86c9ab51aa6cfdfab',5,NULL,NULL,'2026-10-25 00:00:00.000000','7eae82e4-9889-5965-947e-7fb59fafddf2');
INSERT INTO "formula" VALUES(41,2,'b350bdb91d354a548296a18dac05f3506e1255a3c3cade7166e167b586625fb6',2,NULL,NULL,'2026-10-25 00:00:00.000000','b6b45e67-1ca2-5f46-9640-bde0546d24ae');
INSERT INTO "formula" VALUES(42,2,'00e0d45caccfbd48e90fc8ce5ac691641a4f2523079aa8e92720db354bf167d8',3,NULL,NULL,'2026-10-25 00:00:00.000000','abf73973-80ab-5f3f-bbb9-c23be53062f7');
INSERT INTO "formula" VALUES(43,2,'c5a8c4cec893653158f0a83ec852a67ae6af621f8ce2031353ff9aa004141d36',3,NULL,NULL,'2026-10-25 00:00:00.000000','439b3090-b681-59b6-901b-21cd9970be82');
INSERT INTO "formula" VALUES(44,2,'b1e6bd1fe03dc3973886fb5e458c0be1684963844e53ea35773f30e730309978',5,NULL,NULL,'2026-10-25 00:00:00.000000','404a3001-b3f3-5216-9a30-56ee9fc37926');
INSERT INTO "formula" VALUES(45,2,'4c2607a528cea0a1d283891a45695522c4d57595c042f532cce663c4148fac6b',5,NULL,NULL,'2026-10-25 00:00:00.000000','64abd21a-261e-5d8c-96d3-ee7fdbb99b79');
INSERT INTO "formula" VALUES(46,2,'8fdd776bb3a49ee679841fd112568904fd2ff5e13b367cea95d71a8cf26787a4',2,NULL,NULL,'2026-10-25 00:00:00.000000','e404d2a8-168d-5282-b2e9-e12e5421c893');
INSERT INTO "formula" VALUES(47,2,'96c1855c435c54d4e4c5af1cfdb0d2e9686b0c328e6898ae7ddb05b8a71e6ac8',3,NULL,NULL,'2026-10-25 00:00:00.000000','3bf3b3ce-b473-5323-b647-f2f7222d7089');
INSERT INTO "formula" VALUES(48,2,'6cbfe7ee98a74ae26cce7da1f6a07eecad5e73380ff64cd08b08ae84db194537',2,NULL,NULL,'2026-10-25 00:00:00.000000','c41183e0-24ab-58d8-915a-f2db1d7d771d');
INSERT INTO "formula" VALUES(49,2,'297ba3cd6fa47b953f1bd0f69d786d69df86b085bae58129c59a6a9408815bf7',5,NULL,NULL,'2026-10-25 00:00:00.000000','8f9bcb5b-26ea-5904-b26c-2b02bcd2a036');
INSERT INTO "formula" VALUES(50,2,'e84ede8ab541a2d830070b48f47823bcd886b4d62853d55cdc16ef51b903dea8',5,NULL,NULL,'2026-10-25 00:00:00.000000','02f7393d-3d6d-588f-91ec-3703c06f93cb');
INSERT INTO "formula" VALUES(51,2,'b26714fd411daaa521bbaed9e6492305b81702f40b07d2846f7609f4c09d9b8b',4,NULL,NULL,'2026-10-25 00:00:00.000000','7e6980e0-ed88-5143-b358-2718f65f10a4');
INSERT INTO "formula" VALUES(52,2,'092e000509ce0a3e639aab46804eb9c8847e24d25ce7ed93711865bf21a4213a',8,NULL,NULL,'2026-10-25 00:00:00.000000','41448d63-efd2-5178-a064-42708e030650');
INSERT INTO "formula" VALUES(53,2,'10a36130773837e856e4e783a3a41feb42c45d71e1e3dd20265042a199b7c926',3,NULL,NULL,'2026-10-25 00:00:00.000000','3500719a-901e-59e4-b4a7-51b25fd177e5');
INSERT INTO "formula" VALUES(54,2,'75c6e0adf054fe3f861a6c9a2f2e3fa3e296444748572eca9a3d16fc4824659b',9,NULL,NULL,'2026-10-25 00:00:00.000000','a9b0a492-13c8-51a7-b88d-59d550795adf');
INSERT INTO "formula" VALUES(55,2,'edccf848cdd2b186d42dbeff4b908877f9ad4c609fccc7b320e6ff21d2b06787',2,NULL,NULL,'2026-10-25 00:00:00.000000','78b0e5ae-ebe2-5c4c-88a2-0f1ea9d9c226');
INSERT INTO "formula" VALUES(56,2,'4ce2bbfb6096a7be1620e04c9150beffeba377737b1926bab760856107663dc6',5,NULL,NULL,'2026-10-25 00:00:00.000000','04221371-df11-55b5-a8cd-354100320b02');
INSERT INTO "formula" VALUES(57,2,'eca7799f476d2725c7ca2711463f1d21525046e4364a6185457a27f221351a77',4,NULL,NULL,'2026-10-25 00:00:00.000000','a0736f3a-33f0-5a46-a495-5b26b6ab8004');
INSERT INTO "formula" VALUES(58,2,'387141fb4308ed1ad6717a4ebd35a00e610f0fafd30c8131fdd864b3ee0d90c4',5,NULL,NULL,'2026-10-25 00:00:00.000000','8ae8fd8f-d369-56d2-80da-67422b33461e');
INSERT INTO "formula" VALUES(59,2,'fdb8817776ec895bcfa3b8435fb866a4912729d4c23fcb4bab44da511173badc',6,NULL,NULL,'2026-10-25 00:00:00.000000','c82bf709-8e69-5584-9372-31f00d269e89');
INSERT INTO "formula" VALUES(60,2,'ef31e098a7bddfdca2cfeacb26d02de1a5b48c63a0c929feed7dd380a9ab016f',7,NULL,NULL,'2026-10-25 00:00:00.000000','b6c122d2-9e3c-55f8-9ec2-489eaeaccabd');
INSERT INTO "formula" VALUES(61,2,'f3707b5ab715f1c52ea057e18421ce4c12b0a2874e8397e2eee9c40d72f96036',6,NULL,NULL,'2026-10-25 00:00:00.000000','69cd9c29-b634-52b1-b9a8-bc26a69ecb9d');
INSERT INTO "formula" VALUES(62,2,'69f5ef6254485bd470cd794c579fff88eb01be1f93e494fde0acd6afaaf345bb',12,NULL,NULL,'2026-10-25 00:00:00.000000','544de178-2033-5f8d-aae3-d4165ff84f56');
INSERT INTO "formula" VALUES(63,2,'1aa6020ca207a54641a3c9493c1460ed0ffc2b1a2f798cf64f6365bd8a4127f9',7,NULL,NULL,'2026-10-25 00:00:00.000000','ba83ca54-1fa2-5714-98be-61f6309c5013');
INSERT INTO "formula" VALUES(64,2,'ce14deef5fd6740c557afc902344b06009e3532c40445d1677d58ffb27111743',3,NULL,NULL,'2026-10-25 00:00:00.000000','2d43296e-33fd-50be-9e92-a02655d46039');
INSERT INTO "formula" VALUES(65,2,'c774d856c7ebc7e1b506a9494c456c7213e190ab75c836fe204cf79bc80e53fd',3,NULL,NULL,'2026-10-25 00:00:00.000000','224b054d-d15c-5eb1-9a15-32f1eb209f75');
INSERT INTO "formula" VALUES(66,2,'6d2f97039b9fc606c2d8369f8f1e715d36dca25e88a881db1c73cc65b99d8844',7,NULL,NULL,'2026-10-25 00:00:00.000000','012bf5c7-8984-5610-ac4c-aed4afc0e671');
INSERT INTO "formula" VALUES(67,2,'f8bad8051949d37d32d97c4e8abe8098fd9cc43374f08bdb69e7074bba3a41a1',5,NULL,NULL,'2026-10-25 00:00:00.000000','bdfe5e17-c384-5211-90d7-4f1af12bd690');
INSERT INTO "formula" VALUES(68,2,'27eed36c0f208db608fdc5e37e74065f37a1becd82af93e29014f61c6f0d3ef1',5,NULL,NULL,'2026-10-25 00:00:00.000000','704e0b88-00be-5350-934b-7fe60fbeefdd');
INSERT INTO "formula" VALUES(69,2,'69babb7eaf428777893918239d1dd25747339b01d8dd33af810e7ade6887998d',10,NULL,NULL,'2026-10-25 00:00:00.000000','c8d2b804-06d3-52a2-a232-f30641be4618');
INSERT INTO "formula" VALUES(70,2,'1fd62502674ff48577a4157945e91d6a6492ed6c387c7da379bd37e75bd5dfaa',4,NULL,NULL,'2026-10-25 00:00:00.000000','b35a8fb0-784e-5e65-af42-031aef872a51');
INSERT INTO "formula" VALUES(71,2,'42987299756a2f82ab0b1f8b56df441c792a61d0a14b95355fb5c9060c05ab4d',3,NULL,NULL,'2026-10-25 00:00:00.000000','abe90536-ee4f-5364-a2ce-f8e1e2a747a0');
INSERT INTO "formula" VALUES(72,2,'7fbc4e5e3d881add5489aa3b7f39552f3ff7f711123ebc5263ea7481937282b4',6,NULL,NULL,'2026-10-25 00:00:00.000000','917baa2b-7ce2-5cc8-a201-0e57e08b5699');
INSERT INTO "formula" VALUES(73,2,'fdf66c75ad91bbf8593bf6d18917454810b1955c87b8ec704caef858b0d5221d',5,NULL,NULL,'2026-10-25 00:00:00.000000','444c7292-defb-5c61-8834-990c2925c278');
INSERT INTO "formula" VALUES(74,2,'03162e60bbaa48b9afc38ecf18faaf7920bd6157f266f24c7459ddccb47e4360',5,NULL,NULL,'2026-10-25 00:00:00.000000','d4bfaaca-5a31-5b13-94ac-81aadcd996a6');
INSERT INTO "formula" VALUES(75,2,'ef0a5edce081c627674dd05de5989253b3a792c1facedf0a1119cfeab92bafae',8,NULL,NULL,'2026-10-25 00:00:00.000000','121bee01-6a7d-581f-a833-e35946f432d9');
INSERT INTO "formula" VALUES(76,2,'e30e03986ae86a904e8366d3fe658b098a6388556a5f5ce6e0865467e194e510',5,NULL,NULL,'2026-10-25 00:00:00.000000','e3893cfa-12b1-5b37-8bf1-f4e7eed13cd9');
INSERT INTO "formula" VALUES(77,2,'bce62cc521056075cdd0ce1fefa227971e3ee601ce3f4b3b3707122649805d77',7,NULL,NULL,'2026-10-25 00:00:00.000000','3a22a3cb-c66e-5328-bf5f-573faeb95d4a');
INSERT INTO "formula" VALUES(78,2,'df4848dff3efba928eac1f98a8157dfa925df4dea05b36a6797504384f0d83f7',4,NULL,NULL,'2026-10-25 00:00:00.000000','de1abcea-f496-5bdc-94ec-15da48dda2e5');
INSERT INTO "formula" VALUES(79,2,'7b58f904baef198c7c8ca932e4746377818cd4ace048b2e2236f416cd95f7959',5,NULL,NULL,'2026-10-25 00:00:00.000000','b2ac3e43-0fc6-5982-a635-6b2ecc123cb7');
INSERT INTO "formula" VALUES(80,2,'61c680438be16b9d51b993773c5f3de144f506379696c4bfe4f183867e5eb21c',6,NULL,NULL,'2026-10-25 00:00:00.000000','f33dc331-1253-54e8-a886-9347cfbb31b0');
INSERT INTO "formula" VALUES(81,2,'cd8e8528740c97c69f00eabe198adeff19d72db83d83ca08b2bf3f1579677004',7,NULL,NULL,'2026-10-25 00:00:00.000000','a83bfb9b-16dc-5089-a25e-e1a605f0e671');
INSERT INTO "formula" VALUES(82,2,'103160934db996183ec49c5bc037c39c0a00c9b6d520461c1112fa5c4f8df540',7,NULL,NULL,'2026-10-25 00:00:00.000000','f953dcc9-bd71-5680-ab7f-06353309d1d6');
INSERT INTO "formula" VALUES(83,2,'6ed7a0d9069b8f0188d9a2ea27facc51df13ea7039492c6512246549825d7dd7',14,NULL,NULL,'2026-10-25 00:00:00.000000','d6b50efb-2561-526b-86bf-18de61eaab44');
INSERT INTO "formula" VALUES(84,2,'03d73a80a38ccf9e7438084fc7e389daaa12424b9df81edc9a3a21af012eeddd',6,NULL,NULL,'2026-10-25 00:00:00.000000','5aceb8fb-5f4a-5165-ab59-ab7712faca4a');
INSERT INTO "formula" VALUES(85,2,'26eb374f65d092e2e1ebeab12b06956f5074c450c5027908981123c8f56a4f0c',11,NULL,NULL,'2026-10-25 00:00:00.000000','6609fee1-6218-58b7-82c7-354d61b4f350');
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
INSERT INTO "formula_token" VALUES(121,21,0,5,NULL);
INSERT INTO "formula_token" VALUES(122,21,1,1,NULL);
INSERT INTO "formula_token" VALUES(123,21,2,10,NULL);
INSERT INTO "formula_token" VALUES(124,22,0,5,NULL);
INSERT INTO "formula_token" VALUES(125,22,1,5,NULL);
INSERT INTO "formula_token" VALUES(126,22,2,10,NULL);
INSERT INTO "formula_token" VALUES(127,22,3,1,NULL);
INSERT INTO "formula_token" VALUES(128,22,4,2,NULL);
INSERT INTO "formula_token" VALUES(129,22,5,10,NULL);
INSERT INTO "formula_token" VALUES(130,23,0,5,NULL);
INSERT INTO "formula_token" VALUES(131,23,1,2,NULL);
INSERT INTO "formula_token" VALUES(132,23,2,10,NULL);
INSERT INTO "formula_token" VALUES(133,23,3,5,NULL);
INSERT INTO "formula_token" VALUES(134,23,4,10,NULL);
INSERT INTO "formula_token" VALUES(135,23,5,1,NULL);
INSERT INTO "formula_token" VALUES(136,24,0,5,NULL);
INSERT INTO "formula_token" VALUES(137,24,1,10,NULL);
INSERT INTO "formula_token" VALUES(138,24,2,5,NULL);
INSERT INTO "formula_token" VALUES(139,24,3,11,NULL);
INSERT INTO "formula_token" VALUES(140,24,4,4,NULL);
INSERT INTO "formula_token" VALUES(141,24,5,10,NULL);
INSERT INTO "formula_token" VALUES(142,24,6,11,NULL);
INSERT INTO "formula_token" VALUES(143,25,0,5,NULL);
INSERT INTO "formula_token" VALUES(144,25,1,4,NULL);
INSERT INTO "formula_token" VALUES(145,25,2,10,NULL);
INSERT INTO "formula_token" VALUES(146,25,3,11,NULL);
INSERT INTO "formula_token" VALUES(147,25,4,10,NULL);
INSERT INTO "formula_token" VALUES(148,26,0,5,NULL);
INSERT INTO "formula_token" VALUES(149,26,1,4,NULL);
INSERT INTO "formula_token" VALUES(150,26,2,10,NULL);
INSERT INTO "formula_token" VALUES(151,26,3,11,NULL);
INSERT INTO "formula_token" VALUES(152,26,4,11,NULL);
INSERT INTO "formula_token" VALUES(153,27,0,5,NULL);
INSERT INTO "formula_token" VALUES(154,27,1,10,NULL);
INSERT INTO "formula_token" VALUES(155,27,2,3,NULL);
INSERT INTO "formula_token" VALUES(156,27,3,10,NULL);
INSERT INTO "formula_token" VALUES(157,27,4,11,NULL);
INSERT INTO "formula_token" VALUES(158,28,0,5,NULL);
INSERT INTO "formula_token" VALUES(159,28,1,11,NULL);
INSERT INTO "formula_token" VALUES(160,28,2,3,NULL);
INSERT INTO "formula_token" VALUES(161,28,3,10,NULL);
INSERT INTO "formula_token" VALUES(162,28,4,11,NULL);
INSERT INTO "formula_token" VALUES(163,29,0,5,NULL);
INSERT INTO "formula_token" VALUES(164,29,1,5,NULL);
INSERT INTO "formula_token" VALUES(165,29,2,10,NULL);
INSERT INTO "formula_token" VALUES(166,29,3,12,NULL);
INSERT INTO "formula_token" VALUES(167,29,4,5,NULL);
INSERT INTO "formula_token" VALUES(168,29,5,5,NULL);
INSERT INTO "formula_token" VALUES(169,29,6,11,NULL);
INSERT INTO "formula_token" VALUES(170,29,7,12,NULL);
INSERT INTO "formula_token" VALUES(171,29,8,5,NULL);
INSERT INTO "formula_token" VALUES(172,29,9,3,NULL);
INSERT INTO "formula_token" VALUES(173,29,10,10,NULL);
INSERT INTO "formula_token" VALUES(174,29,11,11,NULL);
INSERT INTO "formula_token" VALUES(175,29,12,12,NULL);
INSERT INTO "formula_token" VALUES(176,30,0,5,NULL);
INSERT INTO "formula_token" VALUES(177,30,1,13,NULL);
INSERT INTO "formula_token" VALUES(178,30,2,17,NULL);
INSERT INTO "formula_token" VALUES(179,30,3,8,NULL);
INSERT INTO "formula_token" VALUES(180,30,4,13,NULL);
INSERT INTO "formula_token" VALUES(181,30,5,NULL,0);
INSERT INTO "formula_token" VALUES(182,31,0,5,NULL);
INSERT INTO "formula_token" VALUES(183,31,1,7,NULL);
INSERT INTO "formula_token" VALUES(184,31,2,5,NULL);
INSERT INTO "formula_token" VALUES(185,31,3,13,NULL);
INSERT INTO "formula_token" VALUES(186,31,4,NULL,0);
INSERT INTO "formula_token" VALUES(187,31,5,11,NULL);
INSERT INTO "formula_token" VALUES(188,31,6,5,NULL);
INSERT INTO "formula_token" VALUES(189,31,7,8,NULL);
INSERT INTO "formula_token" VALUES(190,31,8,13,NULL);
INSERT INTO "formula_token" VALUES(191,31,9,NULL,0);
INSERT INTO "formula_token" VALUES(192,31,10,11,NULL);
INSERT INTO "formula_token" VALUES(193,32,0,1,NULL);
INSERT INTO "formula_token" VALUES(194,33,0,2,NULL);
INSERT INTO "formula_token" VALUES(195,33,1,10,NULL);
INSERT INTO "formula_token" VALUES(196,34,0,5,NULL);
INSERT INTO "formula_token" VALUES(197,34,1,10,NULL);
INSERT INTO "formula_token" VALUES(198,34,2,1,NULL);
INSERT INTO "formula_token" VALUES(199,35,0,4,NULL);
INSERT INTO "formula_token" VALUES(200,35,1,10,NULL);
INSERT INTO "formula_token" VALUES(201,35,2,11,NULL);
INSERT INTO "formula_token" VALUES(202,36,0,5,NULL);
INSERT INTO "formula_token" VALUES(203,36,1,11,NULL);
INSERT INTO "formula_token" VALUES(204,36,2,4,NULL);
INSERT INTO "formula_token" VALUES(205,36,3,10,NULL);
INSERT INTO "formula_token" VALUES(206,36,4,11,NULL);
INSERT INTO "formula_token" VALUES(207,37,0,3,NULL);
INSERT INTO "formula_token" VALUES(208,37,1,10,NULL);
INSERT INTO "formula_token" VALUES(209,37,2,11,NULL);
INSERT INTO "formula_token" VALUES(210,38,0,5,NULL);
INSERT INTO "formula_token" VALUES(211,38,1,10,NULL);
INSERT INTO "formula_token" VALUES(212,38,2,12,NULL);
INSERT INTO "formula_token" VALUES(213,39,0,5,NULL);
INSERT INTO "formula_token" VALUES(214,39,1,5,NULL);
INSERT INTO "formula_token" VALUES(215,39,2,11,NULL);
INSERT INTO "formula_token" VALUES(216,39,3,12,NULL);
INSERT INTO "formula_token" VALUES(217,39,4,5,NULL);
INSERT INTO "formula_token" VALUES(218,39,5,3,NULL);
INSERT INTO "formula_token" VALUES(219,39,6,10,NULL);
INSERT INTO "formula_token" VALUES(220,39,7,11,NULL);
INSERT INTO "formula_token" VALUES(221,39,8,12,NULL);
INSERT INTO "formula_token" VALUES(222,40,0,5,NULL);
INSERT INTO "formula_token" VALUES(223,40,1,3,NULL);
INSERT INTO "formula_token" VALUES(224,40,2,10,NULL);
INSERT INTO "formula_token" VALUES(225,40,3,11,NULL);
INSERT INTO "formula_token" VALUES(226,40,4,12,NULL);
INSERT INTO "formula_token" VALUES(227,41,0,13,NULL);
INSERT INTO "formula_token" VALUES(228,41,1,17,NULL);
INSERT INTO "formula_token" VALUES(229,42,0,7,NULL);
INSERT INTO "formula_token" VALUES(230,42,1,13,NULL);
INSERT INTO "formula_token" VALUES(231,42,2,NULL,0);
INSERT INTO "formula_token" VALUES(232,43,0,8,NULL);
INSERT INTO "formula_token" VALUES(233,43,1,13,NULL);
INSERT INTO "formula_token" VALUES(234,43,2,NULL,0);
INSERT INTO "formula_token" VALUES(235,44,0,7,NULL);
INSERT INTO "formula_token" VALUES(236,44,1,5,NULL);
INSERT INTO "formula_token" VALUES(237,44,2,13,NULL);
INSERT INTO "formula_token" VALUES(238,44,3,NULL,0);
INSERT INTO "formula_token" VALUES(239,44,4,11,NULL);
INSERT INTO "formula_token" VALUES(240,45,0,5,NULL);
INSERT INTO "formula_token" VALUES(241,45,1,8,NULL);
INSERT INTO "formula_token" VALUES(242,45,2,13,NULL);
INSERT INTO "formula_token" VALUES(243,45,3,NULL,0);
INSERT INTO "formula_token" VALUES(244,45,4,11,NULL);
INSERT INTO "formula_token" VALUES(245,46,0,13,NULL);
INSERT INTO "formula_token" VALUES(246,46,1,16,NULL);
INSERT INTO "formula_token" VALUES(247,47,0,9,NULL);
INSERT INTO "formula_token" VALUES(248,47,1,15,NULL);
INSERT INTO "formula_token" VALUES(249,47,2,16,NULL);
INSERT INTO "formula_token" VALUES(250,48,0,13,NULL);
INSERT INTO "formula_token" VALUES(251,48,1,15,NULL);
INSERT INTO "formula_token" VALUES(252,49,0,5,NULL);
INSERT INTO "formula_token" VALUES(253,49,1,13,NULL);
INSERT INTO "formula_token" VALUES(254,49,2,15,NULL);
INSERT INTO "formula_token" VALUES(255,49,3,13,NULL);
INSERT INTO "formula_token" VALUES(256,49,4,16,NULL);
INSERT INTO "formula_token" VALUES(257,50,0,5,NULL);
INSERT INTO "formula_token" VALUES(258,50,1,10,NULL);
INSERT INTO "formula_token" VALUES(259,50,2,2,NULL);
INSERT INTO "formula_token" VALUES(260,50,3,2,NULL);
INSERT INTO "formula_token" VALUES(261,50,4,10,NULL);
INSERT INTO "formula_token" VALUES(262,51,0,5,NULL);
INSERT INTO "formula_token" VALUES(263,51,1,2,NULL);
INSERT INTO "formula_token" VALUES(264,51,2,10,NULL);
INSERT INTO "formula_token" VALUES(265,51,3,1,NULL);
INSERT INTO "formula_token" VALUES(266,52,0,5,NULL);
INSERT INTO "formula_token" VALUES(267,52,1,5,NULL);
INSERT INTO "formula_token" VALUES(268,52,2,2,NULL);
INSERT INTO "formula_token" VALUES(269,52,3,10,NULL);
INSERT INTO "formula_token" VALUES(270,52,4,1,NULL);
INSERT INTO "formula_token" VALUES(271,52,5,2,NULL);
INSERT INTO "formula_token" VALUES(272,52,6,2,NULL);
INSERT INTO "formula_token" VALUES(273,52,7,10,NULL);
INSERT INTO "formula_token" VALUES(274,53,0,2,NULL);
INSERT INTO "formula_token" VALUES(275,53,1,2,NULL);
INSERT INTO "formula_token" VALUES(276,53,2,10,NULL);
INSERT INTO "formula_token" VALUES(277,54,0,5,NULL);
INSERT INTO "formula_token" VALUES(278,54,1,5,NULL);
INSERT INTO "formula_token" VALUES(279,54,2,10,NULL);
INSERT INTO "formula_token" VALUES(280,54,3,11,NULL);
INSERT INTO "formula_token" VALUES(281,54,4,5,NULL);
INSERT INTO "formula_token" VALUES(282,54,5,2,NULL);
INSERT INTO "formula_token" VALUES(283,54,6,11,NULL);
INSERT INTO "formula_token" VALUES(284,54,7,2,NULL);
INSERT INTO "formula_token" VALUES(285,54,8,10,NULL);
INSERT INTO "formula_token" VALUES(286,55,0,2,NULL);
INSERT INTO "formula_token" VALUES(287,55,1,11,NULL);
INSERT INTO "formula_token" VALUES(288,56,0,5,NULL);
INSERT INTO "formula_token" VALUES(289,56,1,2,NULL);
INSERT INTO "formula_token" VALUES(290,56,2,11,NULL);
INSERT INTO "formula_token" VALUES(291,56,3,2,NULL);
INSERT INTO "formula_token" VALUES(292,56,4,10,NULL);
INSERT INTO "formula_token" VALUES(293,57,0,4,NULL);
INSERT INTO "formula_token" VALUES(294,57,1,10,NULL);
INSERT INTO "formula_token" VALUES(295,57,2,2,NULL);
INSERT INTO "formula_token" VALUES(296,57,3,10,NULL);
INSERT INTO "formula_token" VALUES(297,58,0,2,NULL);
INSERT INTO "formula_token" VALUES(298,58,1,4,NULL);
INSERT INTO "formula_token" VALUES(299,58,2,10,NULL);
INSERT INTO "formula_token" VALUES(300,58,3,2,NULL);
INSERT INTO "formula_token" VALUES(301,58,4,10,NULL);
INSERT INTO "formula_token" VALUES(302,59,0,5,NULL);
INSERT INTO "formula_token" VALUES(303,59,1,4,NULL);
INSERT INTO "formula_token" VALUES(304,59,2,10,NULL);
INSERT INTO "formula_token" VALUES(305,59,3,2,NULL);
INSERT INTO "formula_token" VALUES(306,59,4,10,NULL);
INSERT INTO "formula_token" VALUES(307,59,5,10,NULL);
INSERT INTO "formula_token" VALUES(308,60,0,5,NULL);
INSERT INTO "formula_token" VALUES(309,60,1,4,NULL);
INSERT INTO "formula_token" VALUES(310,60,2,10,NULL);
INSERT INTO "formula_token" VALUES(311,60,3,2,NULL);
INSERT INTO "formula_token" VALUES(312,60,4,10,NULL);
INSERT INTO "formula_token" VALUES(313,60,5,2,NULL);
INSERT INTO "formula_token" VALUES(314,60,6,10,NULL);
INSERT INTO "formula_token" VALUES(315,61,0,5,NULL);
INSERT INTO "formula_token" VALUES(316,61,1,4,NULL);
INSERT INTO "formula_token" VALUES(317,61,2,10,NULL);
INSERT INTO "formula_token" VALUES(318,61,3,2,NULL);
INSERT INTO "formula_token" VALUES(319,61,4,10,NULL);
INSERT INTO "formula_token" VALUES(320,61,5,1,NULL);
INSERT INTO "formula_token" VALUES(321,62,0,5,NULL);
INSERT INTO "formula_token" VALUES(322,62,1,5,NULL);
INSERT INTO "formula_token" VALUES(323,62,2,4,NULL);
INSERT INTO "formula_token" VALUES(324,62,3,10,NULL);
INSERT INTO "formula_token" VALUES(325,62,4,2,NULL);
INSERT INTO "formula_token" VALUES(326,62,5,10,NULL);
INSERT INTO "formula_token" VALUES(327,62,6,1,NULL);
INSERT INTO "formula_token" VALUES(328,62,7,2,NULL);
INSERT INTO "formula_token" VALUES(329,62,8,4,NULL);
INSERT INTO "formula_token" VALUES(330,62,9,10,NULL);
INSERT INTO "formula_token" VALUES(331,62,10,2,NULL);
INSERT INTO "formula_token" VALUES(332,62,11,10,NULL);
INSERT INTO "formula_token" VALUES(333,63,0,5,NULL);
INSERT INTO "formula_token" VALUES(334,63,1,4,NULL);
INSERT INTO "formula_token" VALUES(335,63,2,10,NULL);
INSERT INTO "formula_token" VALUES(336,63,3,11,NULL);
INSERT INTO "formula_token" VALUES(337,63,4,4,NULL);
INSERT INTO "formula_token" VALUES(338,63,5,11,NULL);
INSERT INTO "formula_token" VALUES(339,63,6,10,NULL);
INSERT INTO "formula_token" VALUES(340,64,0,4,NULL);
INSERT INTO "formula_token" VALUES(341,64,1,11,NULL);
INSERT INTO "formula_token" VALUES(342,64,2,10,NULL);
INSERT INTO "formula_token" VALUES(343,65,0,3,NULL);
INSERT INTO "formula_token" VALUES(344,65,1,11,NULL);
INSERT INTO "formula_token" VALUES(345,65,2,10,NULL);
INSERT INTO "formula_token" VALUES(346,66,0,5,NULL);
INSERT INTO "formula_token" VALUES(347,66,1,3,NULL);
INSERT INTO "formula_token" VALUES(348,66,2,10,NULL);
INSERT INTO "formula_token" VALUES(349,66,3,11,NULL);
INSERT INTO "formula_token" VALUES(350,66,4,3,NULL);
INSERT INTO "formula_token" VALUES(351,66,5,11,NULL);
INSERT INTO "formula_token" VALUES(352,66,6,10,NULL);
INSERT INTO "formula_token" VALUES(353,67,0,5,NULL);
INSERT INTO "formula_token" VALUES(354,67,1,10,NULL);
INSERT INTO "formula_token" VALUES(355,67,2,3,NULL);
INSERT INTO "formula_token" VALUES(356,67,3,11,NULL);
INSERT INTO "formula_token" VALUES(357,67,4,10,NULL);
INSERT INTO "formula_token" VALUES(358,68,0,5,NULL);
INSERT INTO "formula_token" VALUES(359,68,1,11,NULL);
INSERT INTO "formula_token" VALUES(360,68,2,3,NULL);
INSERT INTO "formula_token" VALUES(361,68,3,11,NULL);
INSERT INTO "formula_token" VALUES(362,68,4,10,NULL);
INSERT INTO "formula_token" VALUES(363,69,0,5,NULL);
INSERT INTO "formula_token" VALUES(364,69,1,2,NULL);
INSERT INTO "formula_token" VALUES(365,69,2,3,NULL);
INSERT INTO "formula_token" VALUES(366,69,3,10,NULL);
INSERT INTO "formula_token" VALUES(367,69,4,11,NULL);
INSERT INTO "formula_token" VALUES(368,69,5,4,NULL);
INSERT INTO "formula_token" VALUES(369,69,6,2,NULL);
INSERT INTO "formula_token" VALUES(370,69,7,10,NULL);
INSERT INTO "formula_token" VALUES(371,69,8,2,NULL);
INSERT INTO "formula_token" VALUES(372,69,9,11,NULL);
INSERT INTO "formula_token" VALUES(373,70,0,2,NULL);
INSERT INTO "formula_token" VALUES(374,70,1,3,NULL);
INSERT INTO "formula_token" VALUES(375,70,2,10,NULL);
INSERT INTO "formula_token" VALUES(376,70,3,11,NULL);
INSERT INTO "formula_token" VALUES(377,71,0,5,NULL);
INSERT INTO "formula_token" VALUES(378,71,1,11,NULL);
INSERT INTO "formula_token" VALUES(379,71,2,1,NULL);
INSERT INTO "formula_token" VALUES(380,72,0,5,NULL);
INSERT INTO "formula_token" VALUES(381,72,1,5,NULL);
INSERT INTO "formula_token" VALUES(382,72,2,11,NULL);
INSERT INTO "formula_token" VALUES(383,72,3,1,NULL);
INSERT INTO "formula_token" VALUES(384,72,4,2,NULL);
INSERT INTO "formula_token" VALUES(385,72,5,11,NULL);
INSERT INTO "formula_token" VALUES(386,73,0,4,NULL);
INSERT INTO "formula_token" VALUES(387,73,1,2,NULL);
INSERT INTO "formula_token" VALUES(388,73,2,10,NULL);
INSERT INTO "formula_token" VALUES(389,73,3,2,NULL);
INSERT INTO "formula_token" VALUES(390,73,4,11,NULL);
INSERT INTO "formula_token" VALUES(391,74,0,5,NULL);
INSERT INTO "formula_token" VALUES(392,74,1,2,NULL);
INSERT INTO "formula_token" VALUES(393,74,2,2,NULL);
INSERT INTO "formula_token" VALUES(394,74,3,10,NULL);
INSERT INTO "formula_token" VALUES(395,74,4,10,NULL);
INSERT INTO "formula_token" VALUES(396,75,0,5,NULL);
INSERT INTO "formula_token" VALUES(397,75,1,2,NULL);
INSERT INTO "formula_token" VALUES(398,75,2,2,NULL);
INSERT INTO "formula_token" VALUES(399,75,3,10,NULL);
INSERT INTO "formula_token" VALUES(400,75,4,5,NULL);
INSERT INTO "formula_token" VALUES(401,75,5,2,NULL);
INSERT INTO "formula_token" VALUES(402,75,6,10,NULL);
INSERT INTO "formula_token" VALUES(403,75,7,1,NULL);
INSERT INTO "formula_token" VALUES(404,76,0,5,NULL);
INSERT INTO "formula_token" VALUES(405,76,1,5,NULL);
INSERT INTO "formula_token" VALUES(406,76,2,10,NULL);
INSERT INTO "formula_token" VALUES(407,76,3,1,NULL);
INSERT INTO "formula_token" VALUES(408,76,4,10,NULL);
INSERT INTO "formula_token" VALUES(409,77,0,5,NULL);
INSERT INTO "formula_token" VALUES(410,77,1,5,NULL);
INSERT INTO "formula_token" VALUES(411,77,2,5,NULL);
INSERT INTO "formula_token" VALUES(412,77,3,10,NULL);
INSERT INTO "formula_token" VALUES(413,77,4,1,NULL);
INSERT INTO "formula_token" VALUES(414,77,5,10,NULL);
INSERT INTO "formula_token" VALUES(415,77,6,10,NULL);
INSERT INTO "formula_token" VALUES(416,78,0,3,NULL);
INSERT INTO "formula_token" VALUES(417,78,1,10,NULL);
INSERT INTO "formula_token" VALUES(418,78,2,2,NULL);
INSERT INTO "formula_token" VALUES(419,78,3,10,NULL);
INSERT INTO "formula_token" VALUES(420,79,0,2,NULL);
INSERT INTO "formula_token" VALUES(421,79,1,3,NULL);
INSERT INTO "formula_token" VALUES(422,79,2,10,NULL);
INSERT INTO "formula_token" VALUES(423,79,3,2,NULL);
INSERT INTO "formula_token" VALUES(424,79,4,10,NULL);
INSERT INTO "formula_token" VALUES(425,80,0,5,NULL);
INSERT INTO "formula_token" VALUES(426,80,1,10,NULL);
INSERT INTO "formula_token" VALUES(427,80,2,3,NULL);
INSERT INTO "formula_token" VALUES(428,80,3,10,NULL);
INSERT INTO "formula_token" VALUES(429,80,4,2,NULL);
INSERT INTO "formula_token" VALUES(430,80,5,10,NULL);
INSERT INTO "formula_token" VALUES(431,81,0,5,NULL);
INSERT INTO "formula_token" VALUES(432,81,1,2,NULL);
INSERT INTO "formula_token" VALUES(433,81,2,10,NULL);
INSERT INTO "formula_token" VALUES(434,81,3,3,NULL);
INSERT INTO "formula_token" VALUES(435,81,4,10,NULL);
INSERT INTO "formula_token" VALUES(436,81,5,2,NULL);
INSERT INTO "formula_token" VALUES(437,81,6,10,NULL);
INSERT INTO "formula_token" VALUES(438,82,0,5,NULL);
INSERT INTO "formula_token" VALUES(439,82,1,2,NULL);
INSERT INTO "formula_token" VALUES(440,82,2,3,NULL);
INSERT INTO "formula_token" VALUES(441,82,3,10,NULL);
INSERT INTO "formula_token" VALUES(442,82,4,2,NULL);
INSERT INTO "formula_token" VALUES(443,82,5,10,NULL);
INSERT INTO "formula_token" VALUES(444,82,6,1,NULL);
INSERT INTO "formula_token" VALUES(445,83,0,5,NULL);
INSERT INTO "formula_token" VALUES(446,83,1,5,NULL);
INSERT INTO "formula_token" VALUES(447,83,2,2,NULL);
INSERT INTO "formula_token" VALUES(448,83,3,3,NULL);
INSERT INTO "formula_token" VALUES(449,83,4,10,NULL);
INSERT INTO "formula_token" VALUES(450,83,5,2,NULL);
INSERT INTO "formula_token" VALUES(451,83,6,10,NULL);
INSERT INTO "formula_token" VALUES(452,83,7,1,NULL);
INSERT INTO "formula_token" VALUES(453,83,8,2,NULL);
INSERT INTO "formula_token" VALUES(454,83,9,2,NULL);
INSERT INTO "formula_token" VALUES(455,83,10,3,NULL);
INSERT INTO "formula_token" VALUES(456,83,11,10,NULL);
INSERT INTO "formula_token" VALUES(457,83,12,2,NULL);
INSERT INTO "formula_token" VALUES(458,83,13,10,NULL);
INSERT INTO "formula_token" VALUES(459,84,0,2,NULL);
INSERT INTO "formula_token" VALUES(460,84,1,2,NULL);
INSERT INTO "formula_token" VALUES(461,84,2,3,NULL);
INSERT INTO "formula_token" VALUES(462,84,3,10,NULL);
INSERT INTO "formula_token" VALUES(463,84,4,2,NULL);
INSERT INTO "formula_token" VALUES(464,84,5,10,NULL);
INSERT INTO "formula_token" VALUES(465,85,0,5,NULL);
INSERT INTO "formula_token" VALUES(466,85,1,2,NULL);
INSERT INTO "formula_token" VALUES(467,85,2,2,NULL);
INSERT INTO "formula_token" VALUES(468,85,3,3,NULL);
INSERT INTO "formula_token" VALUES(469,85,4,10,NULL);
INSERT INTO "formula_token" VALUES(470,85,5,2,NULL);
INSERT INTO "formula_token" VALUES(471,85,6,10,NULL);
INSERT INTO "formula_token" VALUES(472,85,7,3,NULL);
INSERT INTO "formula_token" VALUES(473,85,8,10,NULL);
INSERT INTO "formula_token" VALUES(474,85,9,2,NULL);
INSERT INTO "formula_token" VALUES(475,85,10,10,NULL);
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
INSERT INTO "proof" VALUES(7,6,'含意除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','61c9abd2-01a3-5891-827d-39b3cc814f10',0);
INSERT INTO "proof" VALUES(8,7,'矛盾除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','526b4578-d1be-594c-99ce-d742b8ceedcb',0);
INSERT INTO "proof" VALUES(9,8,'否定導入の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','8f2117c3-38ba-5bff-ae06-37b5ac62d3a1',0);
INSERT INTO "proof" VALUES(10,9,'否定除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','4fcba823-33fb-5371-8fb7-865a9c41fe74',0);
INSERT INTO "proof" VALUES(11,10,'連言導入の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','f219596a-4f84-5327-9b71-2b76f0e67150',0);
INSERT INTO "proof" VALUES(12,11,'連言除去（左）の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','5606510e-a679-5dc3-8313-a9dcc380ac80',0);
INSERT INTO "proof" VALUES(13,12,'連言除去（右）の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','a9b93cb1-7864-5fae-a620-15b00ff005b5',0);
INSERT INTO "proof" VALUES(14,13,'選言導入（左）の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','4022a5eb-6ef7-5742-8267-e212b6d57cf1',0);
INSERT INTO "proof" VALUES(15,14,'選言導入（右）の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','a8de14ce-d58c-58bd-8d79-7043a4ec525a',0);
INSERT INTO "proof" VALUES(16,15,'選言除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','bdbbad01-3381-59c2-83e3-8ed2f11fbf09',0);
INSERT INTO "proof" VALUES(17,16,'全称除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','2dd62c96-4903-5d9c-9300-3247a21e41df',0);
INSERT INTO "proof" VALUES(18,17,'存在導入の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','31ba9cdf-7f5d-520c-b852-df818acfe3fd',0);
INSERT INTO "proof" VALUES(19,18,'存在除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','b66745bc-2cf6-581c-ad2a-c0cba0578314',0);
INSERT INTO "proof" VALUES(20,19,'等号代入の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','2d3a40a9-708b-5c13-8eb7-01bd8ce8e9e9',0);
INSERT INTO "proof" VALUES(21,20,'二重否定導入の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','28cbebdd-36a5-537f-837e-6fc72106c0e5',0);
INSERT INTO "proof" VALUES(22,21,'対偶の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','60e16ae4-4e92-506d-a09a-c7347fcaee0b',0);
INSERT INTO "proof" VALUES(23,22,'無矛盾律の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','00f7f869-940e-5646-b5cb-c84f98b97127',0);
INSERT INTO "proof" VALUES(24,23,'連言の交換の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','b0f03c6d-716f-556f-841b-31bcabfa40e2',0);
INSERT INTO "proof" VALUES(25,24,'選言の交換の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','d07f9931-aa62-5907-ae1b-313383820d66',0);
INSERT INTO "proof" VALUES(26,25,'ド・モルガンの証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','f9e072ef-54ce-53ad-b87a-dd3887fd3d31',0);
INSERT INTO "proof" VALUES(27,26,'二重否定除去の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','3d68ef7d-493f-546a-9151-602773e03589',0);
INSERT INTO "proof" VALUES(28,27,'排中律の証明','verified',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','99e8b81a-7b61-5b5b-92a8-561ce29047e4',0);
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
INSERT INTO "proof_identity_sequence" VALUES(6,1);
INSERT INTO "proof_identity_sequence" VALUES(7,1);
INSERT INTO "proof_identity_sequence" VALUES(8,1);
INSERT INTO "proof_identity_sequence" VALUES(9,1);
INSERT INTO "proof_identity_sequence" VALUES(10,1);
INSERT INTO "proof_identity_sequence" VALUES(11,1);
INSERT INTO "proof_identity_sequence" VALUES(12,1);
INSERT INTO "proof_identity_sequence" VALUES(13,1);
INSERT INTO "proof_identity_sequence" VALUES(14,1);
INSERT INTO "proof_identity_sequence" VALUES(15,1);
INSERT INTO "proof_identity_sequence" VALUES(16,1);
INSERT INTO "proof_identity_sequence" VALUES(17,1);
INSERT INTO "proof_identity_sequence" VALUES(18,1);
INSERT INTO "proof_identity_sequence" VALUES(19,1);
INSERT INTO "proof_identity_sequence" VALUES(20,1);
INSERT INTO "proof_identity_sequence" VALUES(21,1);
INSERT INTO "proof_identity_sequence" VALUES(22,1);
INSERT INTO "proof_identity_sequence" VALUES(23,1);
INSERT INTO "proof_identity_sequence" VALUES(24,1);
INSERT INTO "proof_identity_sequence" VALUES(25,1);
INSERT INTO "proof_identity_sequence" VALUES(26,1);
INSERT INTO "proof_identity_sequence" VALUES(27,1);
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
INSERT INTO "proof_step" VALUES(7,0,'premise',16,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(7,1,'premise',10,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(7,2,'rule',18,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(8,0,'premise',32,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(8,1,'axiom',21,NULL,10,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(8,2,'rule',10,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(9,0,'premise',34,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(9,1,'axiom',22,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(9,2,'rule',33,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(10,0,'premise',33,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(10,1,'premise',10,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(10,2,'axiom',23,NULL,12,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(10,3,'rule',34,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(10,4,'rule',32,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(11,0,'premise',10,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(11,1,'premise',18,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(11,2,'axiom',24,NULL,13,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(11,3,'rule',36,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(11,4,'rule',35,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(12,0,'premise',35,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(12,1,'axiom',25,NULL,14,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(12,2,'rule',10,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(13,0,'premise',35,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(13,1,'axiom',26,NULL,15,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(13,2,'rule',18,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(14,0,'premise',10,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(14,1,'axiom',27,NULL,16,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(14,2,'rule',37,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(15,0,'premise',18,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(15,1,'axiom',28,NULL,17,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(15,2,'rule',37,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,0,'premise',37,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,1,'premise',38,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,2,'premise',17,2,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,3,'axiom',29,NULL,18,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,4,'rule',39,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,5,'rule',40,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(16,6,'rule',15,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(17,0,'premise',42,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(17,1,'axiom',3,NULL,3,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(17,2,'rule',41,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(18,0,'premise',41,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(18,1,'axiom',30,NULL,19,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(18,2,'rule',43,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(19,0,'premise',43,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(19,1,'premise',44,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(19,2,'axiom',31,NULL,20,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(19,3,'rule',45,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(19,4,'rule',18,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(20,0,'premise',47,0,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(20,1,'premise',48,1,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(20,2,'axiom',6,NULL,6,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(20,3,'rule',49,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(20,4,'rule',46,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,0,'assumption',10,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,1,'assumption',33,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,2,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,3,'rule',51,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,4,'axiom',52,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,5,'rule',53,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(21,6,'rule',50,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,0,'assumption',16,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,1,'assumption',55,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,2,'assumption',10,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,3,'rule',18,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,4,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,5,'rule',34,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,6,'axiom',22,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,7,'rule',33,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,8,'rule',56,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(22,9,'rule',54,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,0,'assumption',57,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,1,'axiom',59,NULL,14,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,2,'rule',10,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,3,'axiom',60,NULL,15,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,4,'rule',33,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,5,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,6,'rule',61,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,7,'axiom',62,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(23,8,'rule',58,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,0,'assumption',35,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,1,'axiom',25,NULL,14,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,2,'rule',10,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,3,'axiom',26,NULL,15,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,4,'rule',18,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,5,'theorem',64,NULL,NULL,11,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(24,6,'rule',63,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,0,'assumption',37,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,1,'assumption',10,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,2,'axiom',67,NULL,17,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,3,'rule',65,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,4,'rule',67,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,5,'assumption',18,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,6,'axiom',68,NULL,16,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,7,'rule',65,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,8,'rule',68,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,9,'theorem',65,NULL,NULL,16,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(25,10,'rule',66,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,0,'assumption',70,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,1,'assumption',10,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,2,'axiom',27,NULL,16,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,3,'rule',37,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,4,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,5,'rule',34,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,6,'axiom',22,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,7,'rule',33,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,8,'assumption',18,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,9,'axiom',28,NULL,17,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,10,'rule',37,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,11,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,12,'rule',71,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,13,'axiom',72,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,14,'rule',55,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,15,'theorem',73,NULL,NULL,11,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(26,16,'rule',69,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,0,'assumption',53,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,1,'axiom',75,NULL,12,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,2,'rule',51,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,3,'assumption',34,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,4,'axiom',22,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,5,'rule',33,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,6,'rule',32,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,7,'axiom',21,NULL,10,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,8,'rule',10,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,9,'rule',76,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,10,'axiom',77,NULL,8,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,11,'rule',10,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(27,12,'rule',74,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,0,'assumption',79,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,1,'assumption',10,NULL,NULL,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,2,'axiom',80,NULL,16,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,3,'rule',78,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,4,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,5,'rule',34,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,6,'axiom',22,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,7,'rule',33,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,8,'axiom',81,NULL,17,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,9,'rule',78,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,10,'theorem',32,NULL,NULL,10,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,11,'rule',82,NULL,NULL,NULL,3,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,12,'axiom',83,NULL,11,NULL,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,13,'rule',84,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,14,'theorem',85,NULL,NULL,27,NULL,NULL,NULL,'2026-10-25 00:00:00.000000');
INSERT INTO "proof_step" VALUES(28,15,'rule',78,NULL,NULL,NULL,1,NULL,NULL,'2026-10-25 00:00:00.000000');
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
INSERT INTO "proof_step_arg" VALUES(7,2,0,1);
INSERT INTO "proof_step_arg" VALUES(7,2,1,0);
INSERT INTO "proof_step_arg" VALUES(8,2,0,0);
INSERT INTO "proof_step_arg" VALUES(8,2,1,1);
INSERT INTO "proof_step_arg" VALUES(9,2,0,0);
INSERT INTO "proof_step_arg" VALUES(9,2,1,1);
INSERT INTO "proof_step_arg" VALUES(10,3,0,0);
INSERT INTO "proof_step_arg" VALUES(10,3,1,2);
INSERT INTO "proof_step_arg" VALUES(10,4,0,1);
INSERT INTO "proof_step_arg" VALUES(10,4,1,3);
INSERT INTO "proof_step_arg" VALUES(11,3,0,0);
INSERT INTO "proof_step_arg" VALUES(11,3,1,2);
INSERT INTO "proof_step_arg" VALUES(11,4,0,1);
INSERT INTO "proof_step_arg" VALUES(11,4,1,3);
INSERT INTO "proof_step_arg" VALUES(12,2,0,0);
INSERT INTO "proof_step_arg" VALUES(12,2,1,1);
INSERT INTO "proof_step_arg" VALUES(13,2,0,0);
INSERT INTO "proof_step_arg" VALUES(13,2,1,1);
INSERT INTO "proof_step_arg" VALUES(14,2,0,0);
INSERT INTO "proof_step_arg" VALUES(14,2,1,1);
INSERT INTO "proof_step_arg" VALUES(15,2,0,0);
INSERT INTO "proof_step_arg" VALUES(15,2,1,1);
INSERT INTO "proof_step_arg" VALUES(16,4,0,1);
INSERT INTO "proof_step_arg" VALUES(16,4,1,3);
INSERT INTO "proof_step_arg" VALUES(16,5,0,2);
INSERT INTO "proof_step_arg" VALUES(16,5,1,4);
INSERT INTO "proof_step_arg" VALUES(16,6,0,0);
INSERT INTO "proof_step_arg" VALUES(16,6,1,5);
INSERT INTO "proof_step_arg" VALUES(17,2,0,0);
INSERT INTO "proof_step_arg" VALUES(17,2,1,1);
INSERT INTO "proof_step_arg" VALUES(18,2,0,0);
INSERT INTO "proof_step_arg" VALUES(18,2,1,1);
INSERT INTO "proof_step_arg" VALUES(19,3,0,1);
INSERT INTO "proof_step_arg" VALUES(19,3,1,2);
INSERT INTO "proof_step_arg" VALUES(19,4,0,0);
INSERT INTO "proof_step_arg" VALUES(19,4,1,3);
INSERT INTO "proof_step_arg" VALUES(20,3,0,0);
INSERT INTO "proof_step_arg" VALUES(20,3,1,2);
INSERT INTO "proof_step_arg" VALUES(20,4,0,1);
INSERT INTO "proof_step_arg" VALUES(20,4,1,3);
INSERT INTO "proof_step_arg" VALUES(21,2,0,1);
INSERT INTO "proof_step_arg" VALUES(21,2,1,0);
INSERT INTO "proof_step_arg" VALUES(21,3,0,1);
INSERT INTO "proof_step_arg" VALUES(21,3,1,2);
INSERT INTO "proof_step_arg" VALUES(21,5,0,3);
INSERT INTO "proof_step_arg" VALUES(21,5,1,4);
INSERT INTO "proof_step_arg" VALUES(21,6,0,0);
INSERT INTO "proof_step_arg" VALUES(21,6,1,5);
INSERT INTO "proof_step_arg" VALUES(22,3,0,2);
INSERT INTO "proof_step_arg" VALUES(22,3,1,0);
INSERT INTO "proof_step_arg" VALUES(22,4,0,1);
INSERT INTO "proof_step_arg" VALUES(22,4,1,3);
INSERT INTO "proof_step_arg" VALUES(22,5,0,2);
INSERT INTO "proof_step_arg" VALUES(22,5,1,4);
INSERT INTO "proof_step_arg" VALUES(22,7,0,5);
INSERT INTO "proof_step_arg" VALUES(22,7,1,6);
INSERT INTO "proof_step_arg" VALUES(22,8,0,1);
INSERT INTO "proof_step_arg" VALUES(22,8,1,7);
INSERT INTO "proof_step_arg" VALUES(22,9,0,0);
INSERT INTO "proof_step_arg" VALUES(22,9,1,8);
INSERT INTO "proof_step_arg" VALUES(23,2,0,0);
INSERT INTO "proof_step_arg" VALUES(23,2,1,1);
INSERT INTO "proof_step_arg" VALUES(23,4,0,0);
INSERT INTO "proof_step_arg" VALUES(23,4,1,3);
INSERT INTO "proof_step_arg" VALUES(23,5,0,4);
INSERT INTO "proof_step_arg" VALUES(23,5,1,2);
INSERT INTO "proof_step_arg" VALUES(23,6,0,0);
INSERT INTO "proof_step_arg" VALUES(23,6,1,5);
INSERT INTO "proof_step_arg" VALUES(23,8,0,6);
INSERT INTO "proof_step_arg" VALUES(23,8,1,7);
INSERT INTO "proof_step_arg" VALUES(24,2,0,0);
INSERT INTO "proof_step_arg" VALUES(24,2,1,1);
INSERT INTO "proof_step_arg" VALUES(24,4,0,0);
INSERT INTO "proof_step_arg" VALUES(24,4,1,3);
INSERT INTO "proof_step_arg" VALUES(24,5,0,4);
INSERT INTO "proof_step_arg" VALUES(24,5,1,2);
INSERT INTO "proof_step_arg" VALUES(24,6,0,0);
INSERT INTO "proof_step_arg" VALUES(24,6,1,5);
INSERT INTO "proof_step_arg" VALUES(25,3,0,1);
INSERT INTO "proof_step_arg" VALUES(25,3,1,2);
INSERT INTO "proof_step_arg" VALUES(25,4,0,1);
INSERT INTO "proof_step_arg" VALUES(25,4,1,3);
INSERT INTO "proof_step_arg" VALUES(25,7,0,5);
INSERT INTO "proof_step_arg" VALUES(25,7,1,6);
INSERT INTO "proof_step_arg" VALUES(25,8,0,5);
INSERT INTO "proof_step_arg" VALUES(25,8,1,7);
INSERT INTO "proof_step_arg" VALUES(25,9,0,0);
INSERT INTO "proof_step_arg" VALUES(25,9,1,4);
INSERT INTO "proof_step_arg" VALUES(25,9,2,8);
INSERT INTO "proof_step_arg" VALUES(25,10,0,0);
INSERT INTO "proof_step_arg" VALUES(25,10,1,9);
INSERT INTO "proof_step_arg" VALUES(26,3,0,1);
INSERT INTO "proof_step_arg" VALUES(26,3,1,2);
INSERT INTO "proof_step_arg" VALUES(26,4,0,0);
INSERT INTO "proof_step_arg" VALUES(26,4,1,3);
INSERT INTO "proof_step_arg" VALUES(26,5,0,1);
INSERT INTO "proof_step_arg" VALUES(26,5,1,4);
INSERT INTO "proof_step_arg" VALUES(26,7,0,5);
INSERT INTO "proof_step_arg" VALUES(26,7,1,6);
INSERT INTO "proof_step_arg" VALUES(26,10,0,8);
INSERT INTO "proof_step_arg" VALUES(26,10,1,9);
INSERT INTO "proof_step_arg" VALUES(26,11,0,0);
INSERT INTO "proof_step_arg" VALUES(26,11,1,10);
INSERT INTO "proof_step_arg" VALUES(26,12,0,8);
INSERT INTO "proof_step_arg" VALUES(26,12,1,11);
INSERT INTO "proof_step_arg" VALUES(26,14,0,12);
INSERT INTO "proof_step_arg" VALUES(26,14,1,13);
INSERT INTO "proof_step_arg" VALUES(26,15,0,7);
INSERT INTO "proof_step_arg" VALUES(26,15,1,14);
INSERT INTO "proof_step_arg" VALUES(26,16,0,0);
INSERT INTO "proof_step_arg" VALUES(26,16,1,15);
INSERT INTO "proof_step_arg" VALUES(27,2,0,0);
INSERT INTO "proof_step_arg" VALUES(27,2,1,1);
INSERT INTO "proof_step_arg" VALUES(27,5,0,3);
INSERT INTO "proof_step_arg" VALUES(27,5,1,4);
INSERT INTO "proof_step_arg" VALUES(27,6,0,5);
INSERT INTO "proof_step_arg" VALUES(27,6,1,2);
INSERT INTO "proof_step_arg" VALUES(27,8,0,6);
INSERT INTO "proof_step_arg" VALUES(27,8,1,7);
INSERT INTO "proof_step_arg" VALUES(27,9,0,3);
INSERT INTO "proof_step_arg" VALUES(27,9,1,8);
INSERT INTO "proof_step_arg" VALUES(27,11,0,9);
INSERT INTO "proof_step_arg" VALUES(27,11,1,10);
INSERT INTO "proof_step_arg" VALUES(27,12,0,0);
INSERT INTO "proof_step_arg" VALUES(27,12,1,11);
INSERT INTO "proof_step_arg" VALUES(28,3,0,1);
INSERT INTO "proof_step_arg" VALUES(28,3,1,2);
INSERT INTO "proof_step_arg" VALUES(28,4,0,0);
INSERT INTO "proof_step_arg" VALUES(28,4,1,3);
INSERT INTO "proof_step_arg" VALUES(28,5,0,1);
INSERT INTO "proof_step_arg" VALUES(28,5,1,4);
INSERT INTO "proof_step_arg" VALUES(28,7,0,5);
INSERT INTO "proof_step_arg" VALUES(28,7,1,6);
INSERT INTO "proof_step_arg" VALUES(28,9,0,7);
INSERT INTO "proof_step_arg" VALUES(28,9,1,8);
INSERT INTO "proof_step_arg" VALUES(28,10,0,0);
INSERT INTO "proof_step_arg" VALUES(28,10,1,9);
INSERT INTO "proof_step_arg" VALUES(28,11,0,0);
INSERT INTO "proof_step_arg" VALUES(28,11,1,10);
INSERT INTO "proof_step_arg" VALUES(28,13,0,11);
INSERT INTO "proof_step_arg" VALUES(28,13,1,12);
INSERT INTO "proof_step_arg" VALUES(28,15,0,13);
INSERT INTO "proof_step_arg" VALUES(28,15,1,14);
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
INSERT INTO "proof_step_subst_prop" VALUES(21,4,10,33);
INSERT INTO "proof_step_subst_prop" VALUES(22,4,10,18);
INSERT INTO "proof_step_subst_prop" VALUES(23,1,11,33);
INSERT INTO "proof_step_subst_prop" VALUES(23,3,11,33);
INSERT INTO "proof_step_subst_prop" VALUES(23,7,10,57);
INSERT INTO "proof_step_subst_prop" VALUES(24,5,10,18);
INSERT INTO "proof_step_subst_prop" VALUES(24,5,11,10);
INSERT INTO "proof_step_subst_prop" VALUES(25,2,10,18);
INSERT INTO "proof_step_subst_prop" VALUES(25,2,11,10);
INSERT INTO "proof_step_subst_prop" VALUES(25,6,10,18);
INSERT INTO "proof_step_subst_prop" VALUES(25,6,11,10);
INSERT INTO "proof_step_subst_prop" VALUES(25,9,12,65);
INSERT INTO "proof_step_subst_prop" VALUES(26,4,10,37);
INSERT INTO "proof_step_subst_prop" VALUES(26,6,10,10);
INSERT INTO "proof_step_subst_prop" VALUES(26,11,10,37);
INSERT INTO "proof_step_subst_prop" VALUES(26,13,10,18);
INSERT INTO "proof_step_subst_prop" VALUES(26,15,10,33);
INSERT INTO "proof_step_subst_prop" VALUES(26,15,11,55);
INSERT INTO "proof_step_subst_prop" VALUES(27,1,10,33);
INSERT INTO "proof_step_subst_prop" VALUES(27,10,11,32);
INSERT INTO "proof_step_subst_prop" VALUES(28,2,11,33);
INSERT INTO "proof_step_subst_prop" VALUES(28,4,10,78);
INSERT INTO "proof_step_subst_prop" VALUES(28,8,11,33);
INSERT INTO "proof_step_subst_prop" VALUES(28,10,10,78);
INSERT INTO "proof_step_subst_prop" VALUES(28,12,10,79);
INSERT INTO "proof_step_subst_prop" VALUES(28,14,10,78);
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
INSERT INTO "symbol" VALUES(1,'⊥',3,0,1,2,'prefix',NULL,'\bot','矛盾','2026-10-25 00:00:00.000000',16,'3200b32b-2960-5ad9-98b0-3c46eea42f9c');
INSERT INTO "symbol" VALUES(2,'¬',3,1,1,2,'prefix',NULL,'\neg','否定','2026-10-25 00:00:00.000000',30,'7ef55380-cb00-59f7-989f-1347cab26b12');
INSERT INTO "symbol" VALUES(3,'∨',3,2,1,2,'infix',30,'\vee','選言','2026-10-25 00:00:00.000000',20,'e9ab484b-d683-5276-987a-af3df5a6e8e9');
INSERT INTO "symbol" VALUES(4,'∧',3,2,1,2,'infix',40,'\wedge','連言','2026-10-25 00:00:00.000000',15,'473e2256-e6c2-5c2a-b45b-7c39f69519e1');
INSERT INTO "symbol" VALUES(5,'→',3,2,1,2,'infix',20,'\implies','含意','2026-10-25 00:00:00.000000',60,'e72831d9-19bc-5094-abd7-359f275f87a1');
INSERT INTO "symbol" VALUES(6,'↔',3,2,1,2,'infix',10,'\iff','同値','2026-10-25 00:00:00.000000',1,'f4243ce5-6563-52e2-ac75-15de5e49cdec');
INSERT INTO "symbol" VALUES(7,'∀',4,1,1,2,'prefix',NULL,'\forall','整形式な項すべてを走る全称量化','2026-10-25 00:00:00.000000',6,'893f7c1c-3e22-564f-a976-0a8e8e241f62');
INSERT INTO "symbol" VALUES(8,'∃',4,1,1,2,'prefix',NULL,'\exists','整形式な項すべてを走る存在量化','2026-10-25 00:00:00.000000',4,'b299df13-8ca1-5327-9b4c-f08b1231a678');
INSERT INTO "symbol" VALUES(9,'=',2,2,1,2,'infix',50,'=','等号','2026-10-25 00:00:00.000000',3,'9c6f5697-7475-52bd-b600-b981e924af62');
INSERT INTO "symbol" VALUES(10,'φ',7,0,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',63,'43c9c73e-69f5-500a-ba17-852af85be0b7');
INSERT INTO "symbol" VALUES(11,'ψ',7,0,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',35,'056bb080-b4a4-5b6c-a651-86b3309dcda6');
INSERT INTO "symbol" VALUES(12,'χ',7,0,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',7,'8e86446f-fb4f-529e-be9c-3ff070066779');
INSERT INTO "symbol" VALUES(13,'φ¹',7,1,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',13,'9cbf22fc-7169-5d86-806b-e21c083d70b1');
INSERT INTO "symbol" VALUES(14,'ψ¹',7,1,0,2,'prefix',NULL,NULL,NULL,'2026-10-25 00:00:00.000000',1,'2efc9d40-a273-5e41-8315-4de58dfabad3');
INSERT INTO "symbol" VALUES(15,'x',6,0,0,2,'prefix',NULL,'x','シード用自由項変数','2026-10-25 00:00:00.000000',5,'58f571b2-5a2d-51ed-8fbf-7e5e6494d147');
INSERT INTO "symbol" VALUES(16,'y',6,0,0,2,'prefix',NULL,'y','シード用自由項変数','2026-10-25 00:00:00.000000',4,'28ffc497-17bf-56b0-b792-3b4f3882539a');
INSERT INTO "symbol" VALUES(17,'t',6,0,0,2,'prefix',NULL,'t','シード用自由項変数','2026-10-25 00:00:00.000000',3,'4b3303de-7abf-5ee7-b37a-4dc01d43665c');
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
INSERT INTO "theorem" VALUES(6,'含意除去',18,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','204f2e8d-a382-53f7-90d2-13fef1694dc4',2);
INSERT INTO "theorem" VALUES(7,'矛盾除去',10,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','ca86f918-df2e-5c29-a5c6-9a5f8a50b2d0',2);
INSERT INTO "theorem" VALUES(8,'否定導入',33,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','b5bb1f3d-d9c8-5193-a996-b6fd8cb8abed',2);
INSERT INTO "theorem" VALUES(9,'否定除去',32,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','912e0f62-3d26-5d58-8c83-9f8594e9d12b',2);
INSERT INTO "theorem" VALUES(10,'連言導入',35,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','80c0a32c-8d4c-5544-bfdc-9c26f195fa4a',2);
INSERT INTO "theorem" VALUES(11,'連言除去（左）',10,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','dc6b5e06-5aac-585d-969f-232d5186e0af',2);
INSERT INTO "theorem" VALUES(12,'連言除去（右）',18,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','847bcc61-4404-5b6b-9942-9c1d0db923fa',2);
INSERT INTO "theorem" VALUES(13,'選言導入（左）',37,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','a1bc68ad-3648-59c9-83e0-f2f47f135c1d',2);
INSERT INTO "theorem" VALUES(14,'選言導入（右）',37,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','b5e9e2e5-3717-5e77-bdfc-be98f622ef15',2);
INSERT INTO "theorem" VALUES(15,'選言除去',15,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','486e4059-f93e-5ec3-99cc-c1b32da1df89',2);
INSERT INTO "theorem" VALUES(16,'全称除去',41,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','286262b1-aa7a-5a33-b903-49817ffa3014',2);
INSERT INTO "theorem" VALUES(17,'存在導入',43,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','c63ff02a-53f6-5c27-b365-dbdf9b51fde9',2);
INSERT INTO "theorem" VALUES(18,'存在除去',18,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','f3187b15-0968-5581-8488-cac0ac214c8f',2);
INSERT INTO "theorem" VALUES(19,'等号代入',46,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','2b6d9081-0e3d-52d1-8dec-ebd196e6c868',2);
INSERT INTO "theorem" VALUES(20,'二重否定導入',50,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','446fa27a-a649-5b75-b963-8767142fd1d8',2);
INSERT INTO "theorem" VALUES(21,'対偶',54,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','40bb2184-a227-51d1-b2fa-f13bc750a3b8',2);
INSERT INTO "theorem" VALUES(22,'無矛盾律',58,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','3d9f0465-e6c9-51b6-b879-7ef12c36c650',2);
INSERT INTO "theorem" VALUES(23,'連言の交換',63,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','e33874c3-920e-51e0-8f41-05a34124d716',2);
INSERT INTO "theorem" VALUES(24,'選言の交換',66,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','d8a37c38-9d9f-55dd-b11c-da576c9a6303',2);
INSERT INTO "theorem" VALUES(25,'ド・モルガン',69,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','8f8c85b5-b86b-549e-93ae-76bfc3b2af5f',2);
INSERT INTO "theorem" VALUES(26,'二重否定除去',74,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','f5c5f552-680f-5b3a-9ccf-e75047358abc',2);
INSERT INTO "theorem" VALUES(27,'排中律',78,'proven','教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。各証明は使用した公理に相対的に妥当です。',NULL,'2026-10-25 00:00:00.000000','2026-10-25 00:00:00.000000','ebae5c99-c236-5329-a855-f5b4806edb16',2);
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
INSERT INTO "theorem_premise" VALUES(6,0,16);
INSERT INTO "theorem_premise" VALUES(6,1,10);
INSERT INTO "theorem_premise" VALUES(7,0,32);
INSERT INTO "theorem_premise" VALUES(8,0,34);
INSERT INTO "theorem_premise" VALUES(9,0,33);
INSERT INTO "theorem_premise" VALUES(9,1,10);
INSERT INTO "theorem_premise" VALUES(10,0,10);
INSERT INTO "theorem_premise" VALUES(10,1,18);
INSERT INTO "theorem_premise" VALUES(11,0,35);
INSERT INTO "theorem_premise" VALUES(12,0,35);
INSERT INTO "theorem_premise" VALUES(13,0,10);
INSERT INTO "theorem_premise" VALUES(14,0,18);
INSERT INTO "theorem_premise" VALUES(15,0,37);
INSERT INTO "theorem_premise" VALUES(15,1,38);
INSERT INTO "theorem_premise" VALUES(15,2,17);
INSERT INTO "theorem_premise" VALUES(16,0,42);
INSERT INTO "theorem_premise" VALUES(17,0,41);
INSERT INTO "theorem_premise" VALUES(18,0,43);
INSERT INTO "theorem_premise" VALUES(18,1,44);
INSERT INTO "theorem_premise" VALUES(19,0,47);
INSERT INTO "theorem_premise" VALUES(19,1,48);
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
