# Agent Demonstration - Executed Results

- **Run:** 2026-11-16 00:03:17
- **Ontology file:** `hospital_ontology.owl`
- **Reasoner:** HermiT (owlready2)
- **Result:** 38/38 checks passed

Each answer below was generated at runtime by querying the OWL graph. The *expected facts* column lists the facts that the automated check looked for; they were not supplied to the agent.

| # | Category | Question | Result |
|---|----------|----------|--------|
| 1 | entity lookup | Who is John Miller? | PASS |
| 2 | entity lookup | Who is Dr. Emily Davis? | PASS |
| 3 | class query | What is a Cardiologist? | PASS |
| 4 | class query | List all subclasses of Doctor. | PASS |
| 5 | class hierarchy | Is Pneumonia a subclass of Disease? | PASS |
| 6 | class instances | List all chronic diseases. | PASS |
| 7 | relationship | Who is the doctor of Robert Brown? | PASS |
| 8 | relationship | Which diseases does Dr. Patel treat? | PASS |
| 9 | relationship | Which patients does Dr. Patel treat? | PASS |
| 10 | attribute | What is John Miller's blood group? | PASS |
| 11 | attribute | How old is Emma Wilson? | PASS |
| 12 | attribute | What is Dr. Patel's license number? | PASS |
| 13 | attribute | What is the dosage of Metformin? | PASS |
| 14 | attribute | What is the cost of Appointment A-1001? | PASS |
| 15 | multi-hop | Which symptoms are caused by diseases that John Miller has? | PASS |
| 16 | multi-hop / transitive | Which hospital does Dr. Patel work at? | PASS |
| 17 | multi-hop / transitive | Which hospital is the Cardiac ICU part of? | PASS |
| 18 | multi-hop | Which doctors work in departments that are part of City General Hospital? | PASS |
| 19 | multi-hop | Which insurance plans cover diseases that Robert Brown has? | PASS |
| 20 | symmetric property | Which medications interact with Aspirin? | PASS |
| 21 | multi-hop | Which medications interact with the medication prescribed to Robert Brown? | PASS |
| 22 | inverse property | Who is the head of the Cardiology department? | PASS |
| 23 | inverse property | Which patients are treated by a Cardiologist? | PASS |
| 24 | relationship | Which patients have appointments with Dr. Michael Smith? | PASS |
| 25 | aggregation | How many patients are there? | PASS |
| 26 | aggregation | How many patients have diabetes? | PASS |
| 27 | aggregation | How many appointments does Dr. Michael Smith have? | PASS |
| 28 | reasoning | Which patients are senior patients? | PASS |
| 29 | reasoning | Is John Miller a senior patient? | PASS |
| 30 | superlative | Who is the oldest patient? | PASS |
| 31 | relationship path | What is the relationship between John Miller and Dr. Alice Chen? | PASS |
| 32 | attribute | Which diseases affect the respiratory system? | PASS |
| 33 | relationship | Which patients are allergic to Aspirin? | PASS |
| 34 | aggregation | Which patients have more than one disease? | PASS |
| 35 | schema | List all object properties. | PASS |
| 36 | unknown | What is the capital of France? | PASS |
| 37 | unknown | Who is the CEO of Google? | PASS |
| 38 | unknown | What is the population of Springfield? | PASS |

## Detailed question / answer log

### Q1. Who is John Miller?

- **Category:** entity lookup
- **Intent detected:** `individual_description` (confidence 0.99)
- **Status:** PASS (7.096 s)
- **Expected facts:** John Miller, P-1001, Type 2 Diabetes, Hypertension, O+, Dr. Alice Chen

**Agent answer:**

> **John Miller** (`p001`) — Patient
> - Patient ID: P-1001
> - Age: 68
> - Gender: male
> - Blood group: O+
> - Phone: +1-555-1001
> - Diagnoses: Type 2 Diabetes and Hypertension
> - Symptoms: Fatigue, Excessive Thirst, and Frequent Urination
> - Treated by: Dr. Alice Chen and Dr. Nina Rossi
> - Insurance: BlueCare
> - Appointments: 2
> - Medications: Metformin
> - Inferred by HermiT: Patient With Comorbidities, Diabetes Patient, Cardiovascular Patient, and Senior Patient

**SPARQL used:**

```sparql
SELECT ?p ?o WHERE { h:p001 ?p ?o }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p001 http://www.w3.org/1999/02/22-rdf-syntax-ns#type http://www.w3.org/2002/07/owl#NamedIndividual
http://example.org/hospital#p001 http://www.w3.org/1999/02/22-rdf-syntax-ns#type http://example.org/hospital#Patient
http://example.org/hospital#p001 http://www.w3.org/2000/01/rdf-schema#label John Miller
http://example.org/hospital#p001 http://example.org/hospital#name John Miller
http://example.org/hospital#p001 http://example.org/hospital#patientId P-1001
http://example.org/hospital#p001 http://example.org/hospital#age 68
```

### Q2. Who is Dr. Emily Davis?

- **Category:** entity lookup
- **Intent detected:** `individual_description` (confidence 0.99)
- **Status:** PASS (0.167 s)
- **Expected facts:** Surgeon, Surgery, Appendicitis, James Taylor

**Agent answer:**

> **Dr. Emily Davis** (`d005`) — Surgeon
> - Doctor ID: MD-1005
> - Specialty: General Surgery
> - License: MD-1005
> - Phone: +1-555-0105
> - Email: emily.davis@stmary.example.org
> - Works in: Surgery (St. Mary's Hospital)
> - Treats patients: James Taylor
> - Treats diseases: Appendicitis
> - Head of: Surgery
> - Inferred by HermiT: Department Head

**SPARQL used:**

```sparql
SELECT ?p ?o WHERE { h:d005 ?p ?o }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#d005 http://www.w3.org/1999/02/22-rdf-syntax-ns#type http://www.w3.org/2002/07/owl#NamedIndividual
http://example.org/hospital#d005 http://www.w3.org/1999/02/22-rdf-syntax-ns#type http://example.org/hospital#Surgeon
http://example.org/hospital#d005 http://www.w3.org/2000/01/rdf-schema#label Dr. Emily Davis
http://example.org/hospital#d005 http://example.org/hospital#name Emily Davis
http://example.org/hospital#d005 http://example.org/hospital#doctorId MD-1005
http://example.org/hospital#d005 http://example.org/hospital#licenseNumber MD-1005
```

### Q3. What is a Cardiologist?

- **Category:** class query
- **Intent detected:** `class_description` (confidence 0.98)
- **Status:** PASS (0.205 s)
- **Expected facts:** Cardiologist, Doctor, Dr. Rajesh Patel

**Agent answer:**

> **Cardiologist**
> - Subclass of: Doctor
> - Individuals: 2 (e.g. Dr. James Wilson and Dr. Rajesh Patel)

### Q4. List all subclasses of Doctor.

- **Category:** class query
- **Intent detected:** `subclasses` (confidence 1.00)
- **Status:** PASS (0.123 s)
- **Expected facts:** Cardiologist, Surgeon, Neurologist, General Practitioner

**Agent answer:**

> **All subclasses of Doctor**
> - Busy Doctor
> - Cardiologist
> - Department Head
> - Endocrinologist
> - General Practitioner
> - Neurologist
> - Oncologist
> - Orthopedist
> - Pediatrician
> - Pulmonologist
> - Surgeon

**SPARQL used:**

```sparql
SELECT ?c WHERE { ?c rdfs:subClassOf+ h:Doctor }
```

### Q5. Is Pneumonia a subclass of Disease?

- **Category:** class hierarchy
- **Intent detected:** `subclass_check` (confidence 1.00)
- **Status:** PASS (0.017 s)
- **Expected facts:** Yes, Pneumonia, Disease

**Agent answer:**

> **Yes.** Pneumonia is a Disease — its recorded types (Infectious Disease, Respiratory Disease, and Acute Disease) are subclasses of Disease.

**SPARQL used:**

```sparql
ASK { h:Pneumonia rdf:type/rdfs:subClassOf* h:Disease }
```

### Q6. List all chronic diseases.

- **Category:** class instances
- **Intent detected:** `instances` (confidence 1.00)
- **Status:** PASS (0.008 s)
- **Expected facts:** Type 2 Diabetes, Asthma, COPD, Alzheimer's Disease

**Agent answer:**

> **Chronic Disease** individuals (7):
> - Alzheimer's Disease (`AlzheimerDisease`)
> - Asthma (`Asthma`)
> - COPD (`COPD`)
> - Hypertension (`Hypertension`)
> - Osteoarthritis (`Osteoarthritis`)
> - Type 1 Diabetes (`Type1Diabetes`)
> - Type 2 Diabetes (`Type2Diabetes`)

### Q7. Who is the doctor of Robert Brown?

- **Category:** relationship
- **Intent detected:** `generic_relation` (confidence 0.90)
- **Status:** PASS (0.398 s)
- **Expected facts:** Robert Brown, Dr. Rajesh Patel

**Agent answer:**

> **Robert Brown** -> treated by -> Dr. Rajesh Patel.

**SPARQL used:**

```sparql
SELECT ?o WHERE { h:p003 h:treatedBy ?o }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p003 http://example.org/hospital#treatedBy http://example.org/hospital#d002
```

### Q8. Which diseases does Dr. Patel treat?

- **Category:** relationship
- **Intent detected:** `diseases_treated_by_doctor` (confidence 0.98)
- **Status:** PASS (0.154 s)
- **Expected facts:** Coronary Artery Disease, Hypertension

**Agent answer:**

> **Dr. Rajesh Patel** treats: Coronary Artery Disease and Hypertension.

**SPARQL used:**

```sparql
SELECT ?d WHERE { h:d002 h:treatsDisease ?d }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#d002 http://example.org/hospital#treatsDisease http://example.org/hospital#CoronaryArteryDisease
http://example.org/hospital#d002 http://example.org/hospital#treatsDisease http://example.org/hospital#Hypertension
```

### Q9. Which patients does Dr. Patel treat?

- **Category:** relationship
- **Intent detected:** `patients_of_doctor` (confidence 0.98)
- **Status:** PASS (0.231 s)
- **Expected facts:** Robert Brown

**Agent answer:**

> **Dr. Rajesh Patel** treats: Robert Brown.

**SPARQL used:**

```sparql
SELECT ?p WHERE { ?p h:treatedBy h:d002 }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p003 http://example.org/hospital#treatedBy http://example.org/hospital#d002
```

### Q10. What is John Miller's blood group?

- **Category:** attribute
- **Intent detected:** `attribute` (confidence 0.98)
- **Status:** PASS (0.101 s)
- **Expected facts:** O+

**Agent answer:**

> **Blood group of John Miller:** **O+**

**SPARQL used:**

```sparql
SELECT ?v WHERE { h:p001 h:bloodGroup ?v }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p001 http://example.org/hospital#bloodGroup O+
```

### Q11. How old is Emma Wilson?

- **Category:** attribute
- **Intent detected:** `attribute` (confidence 0.98)
- **Status:** PASS (0.004 s)
- **Expected facts:** 34

**Agent answer:**

> **Age of Emma Wilson:** **34**

**SPARQL used:**

```sparql
SELECT ?v WHERE { h:p002 h:age ?v }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p002 http://example.org/hospital#age 34
```

### Q12. What is Dr. Patel's license number?

- **Category:** attribute
- **Intent detected:** `attribute` (confidence 0.98)
- **Status:** PASS (0.007 s)
- **Expected facts:** MD-1002

**Agent answer:**

> **License number of Dr. Rajesh Patel:** **MD-1002**

**SPARQL used:**

```sparql
SELECT ?v WHERE { h:d002 h:licenseNumber ?v }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#d002 http://example.org/hospital#licenseNumber MD-1002
```

### Q13. What is the dosage of Metformin?

- **Category:** attribute
- **Intent detected:** `attribute` (confidence 0.98)
- **Status:** PASS (0.005 s)
- **Expected facts:** 500 mg

**Agent answer:**

> **Dosage of Metformin:** **500 mg**

**SPARQL used:**

```sparql
SELECT ?v WHERE { h:Metformin h:dosage ?v }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#Metformin http://example.org/hospital#dosage 500 mg
```

### Q14. What is the cost of Appointment A-1001?

- **Category:** attribute
- **Intent detected:** `attribute` (confidence 0.98)
- **Status:** PASS (0.003 s)
- **Expected facts:** 120

**Agent answer:**

> **Cost of Appointment A-1001:** **120.00**

**SPARQL used:**

```sparql
SELECT ?v WHERE { h:apt001 h:cost ?v }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#apt001 http://example.org/hospital#cost 120.00
```

### Q15. Which symptoms are caused by diseases that John Miller has?

- **Category:** multi-hop
- **Intent detected:** `symptoms_from_patient_diseases` (confidence 0.97)
- **Status:** PASS (0.018 s)
- **Expected facts:** Excessive Thirst, Frequent Urination, Headache, Blurred Vision

**Agent answer:**

> John Miller has **Type 2 Diabetes and Hypertension**. Symptoms caused by these diseases: **Excessive Thirst, Frequent Urination, Fatigue, Headache, and Blurred Vision**.

**SPARQL used:**

```sparql
SELECT DISTINCT ?s WHERE { h:p001 h:diagnosedWith ?d . ?d h:causes ?s }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p001 http://example.org/hospital#diagnosedWith http://example.org/hospital#Type2Diabetes
http://example.org/hospital#p001 http://example.org/hospital#diagnosedWith http://example.org/hospital#Hypertension
http://example.org/hospital#Type2Diabetes http://example.org/hospital#causes http://example.org/hospital#ExcessiveThirst
http://example.org/hospital#Type2Diabetes http://example.org/hospital#causes http://example.org/hospital#FrequentUrination
http://example.org/hospital#Type2Diabetes http://example.org/hospital#causes http://example.org/hospital#Fatigue
http://example.org/hospital#Hypertension http://example.org/hospital#causes http://example.org/hospital#Headache
```

### Q16. Which hospital does Dr. Patel work at?

- **Category:** multi-hop / transitive
- **Intent detected:** `hospital_of_doctor` (confidence 0.98)
- **Status:** PASS (0.107 s)
- **Expected facts:** Cardiology, St. Mary's Hospital

**Agent answer:**

> Dr. Rajesh Patel works in **Cardiology**, which is part of **St. Mary's Hospital**. The doctor is also affiliated with St. Mary's Hospital.

**SPARQL used:**

```sparql
SELECT ?h WHERE { h:d002 h:worksIn/h:partOf ?h . ?h rdf:type/rdfs:subClassOf* h:Hospital }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#d002 http://example.org/hospital#worksIn http://example.org/hospital#dept_cardio
http://example.org/hospital#d002 http://example.org/hospital#affiliatedWith http://example.org/hospital#hosp_stmary
```

### Q17. Which hospital is the Cardiac ICU part of?

- **Category:** multi-hop / transitive
- **Intent detected:** `generic_relation` (confidence 0.85)
- **Status:** PASS (0.715 s)
- **Expected facts:** St. Mary's Hospital

**Agent answer:**

> **Cardiac ICU** is connected to St. Mary's Hospital via: Cardiac ICU -> [part of] Cardiology -> [part of] St. Mary's Hospital.

**SPARQL used:**

```sparql
SELECT ?x WHERE { h:ward_cardio_icu h:partOf/h:partOf ?x . ?x rdf:type/rdfs:subClassOf* h:Hospital }
```

### Q18. Which doctors work in departments that are part of City General Hospital?

- **Category:** multi-hop
- **Intent detected:** `workers_in_hospital` (confidence 0.97)
- **Status:** PASS (0.201 s)
- **Expected facts:** Dr. James Wilson

**Agent answer:**

> Doctors whose department is part of **City General Hospital**: Dr. James Wilson.

**SPARQL used:**

```sparql
SELECT DISTINCT ?w WHERE { ?d h:partOf h:hosp_city . ?w h:worksIn ?d }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#n004 http://example.org/hospital#worksIn http://example.org/hospital#dept_cardio_city
http://example.org/hospital#d010 http://example.org/hospital#worksIn http://example.org/hospital#dept_cardio_city
```

### Q19. Which insurance plans cover diseases that Robert Brown has?

- **Category:** multi-hop
- **Intent detected:** `insurance_coverage` (confidence 0.97)
- **Status:** PASS (0.118 s)
- **Expected facts:** BlueCare, MediGold, Coronary Artery Disease

**Agent answer:**

> **Robert Brown** is insured by MediGold.
> Insurance plans covering the patient's recorded diseases:
> - MedicarePlus covers Coronary Artery Disease
> - BlueCare covers Coronary Artery Disease and Hypertension
> - MediGold covers Coronary Artery Disease

**SPARQL used:**

```sparql
SELECT ?plan ?d WHERE { h:p003 h:diagnosedWith ?d . ?plan h:coversDisease ?d }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#ins_medicareplus http://example.org/hospital#coversDisease http://example.org/hospital#CoronaryArteryDisease
http://example.org/hospital#ins_bluecare http://example.org/hospital#coversDisease http://example.org/hospital#CoronaryArteryDisease
http://example.org/hospital#ins_medigold http://example.org/hospital#coversDisease http://example.org/hospital#CoronaryArteryDisease
http://example.org/hospital#ins_bluecare http://example.org/hospital#coversDisease http://example.org/hospital#Hypertension
```

### Q20. Which medications interact with Aspirin?

- **Category:** symmetric property
- **Intent detected:** `drug_interactions` (confidence 0.98)
- **Status:** PASS (0.187 s)
- **Expected facts:** Warfarin

**Agent answer:**

> **Aspirin** interacts with: Warfarin.

**SPARQL used:**

```sparql
SELECT ?o WHERE { { h:Aspirin h:interactsWith ?o } UNION { ?o h:interactsWith h:Aspirin } }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#Aspirin http://example.org/hospital#interactsWith http://example.org/hospital#Warfarin
```

### Q21. Which medications interact with the medication prescribed to Robert Brown?

- **Category:** multi-hop
- **Intent detected:** `interactions_of_patient_meds` (confidence 0.97)
- **Status:** PASS (0.145 s)
- **Expected facts:** Warfarin, Aspirin

**Agent answer:**

> **Robert Brown** takes: Aspirin and Atorvastatin.
> 
> Recorded interactions:
> - Aspirin interacts with Warfarin

**SPARQL used:**

```sparql
SELECT ?m ?o WHERE { ?m h:prescribedFor h:p003 . { ?m h:interactsWith ?o } UNION { ?o h:interactsWith ?m } }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#Aspirin http://example.org/hospital#interactsWith http://example.org/hospital#Warfarin
```

### Q22. Who is the head of the Cardiology department?

- **Category:** inverse property
- **Intent detected:** `head_of_department` (confidence 0.98)
- **Status:** PASS (0.104 s)
- **Expected facts:** Dr. Rajesh Patel

**Agent answer:**

> The head of **Cardiology** is Dr. Rajesh Patel.

**SPARQL used:**

```sparql
SELECT ?d WHERE { ?d h:headOf h:dept_cardio }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#d002 http://example.org/hospital#headOf http://example.org/hospital#dept_cardio
```

### Q23. Which patients are treated by a Cardiologist?

- **Category:** inverse property
- **Intent detected:** `patients_by_specialty` (confidence 0.97)
- **Status:** PASS (0.1 s)
- **Expected facts:** Robert Brown, Henry Moore

**Agent answer:**

> Patients treated by a **Cardiologist**: Henry Moore and Robert Brown.

**SPARQL used:**

```sparql
SELECT DISTINCT ?p WHERE { ?p h:treatedBy ?d . ?d rdf:type/rdfs:subClassOf* h:Cardiologist }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p012 http://example.org/hospital#treatedBy http://example.org/hospital#d010
http://example.org/hospital#p003 http://example.org/hospital#treatedBy http://example.org/hospital#d002
```

### Q24. Which patients have appointments with Dr. Michael Smith?

- **Category:** relationship
- **Intent detected:** `patients_with_appointment` (confidence 0.97)
- **Status:** PASS (0.085 s)
- **Expected facts:** David Lee, Emma Wilson, Noah White

**Agent answer:**

> Patients with an appointment with **Dr. Michael Smith**: David Lee, Emma Wilson, and Noah White.

**SPARQL used:**

```sparql
SELECT DISTINCT ?p WHERE { ?a h:withDoctor h:d004 . ?a h:forPatient ?p }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p011 http://example.org/hospital#hasAppointment http://example.org/hospital#apt012
http://example.org/hospital#p002 http://example.org/hospital#hasAppointment http://example.org/hospital#apt003
http://example.org/hospital#p005 http://example.org/hospital#hasAppointment http://example.org/hospital#apt006
```

### Q25. How many patients are there?

- **Category:** aggregation
- **Intent detected:** `count_instances` (confidence 1.00)
- **Status:** PASS (0.095 s)
- **Expected facts:** 12

**Agent answer:**

> There are **12** patients in the ontology.

### Q26. How many patients have diabetes?

- **Category:** aggregation
- **Intent detected:** `count_patients_with_disease` (confidence 0.95)
- **Status:** PASS (0.026 s)
- **Expected facts:** 2

**Agent answer:**

> **2** patient(s) have a disease of type **Diabetes**.

### Q27. How many appointments does Dr. Michael Smith have?

- **Category:** aggregation
- **Intent detected:** `count_relation` (confidence 0.95)
- **Status:** PASS (0.345 s)
- **Expected facts:** 3, A-1003, A-1006, A-1012

**Agent answer:**

> Dr. Michael Smith has **3** appointments: Appointment A-1003, Appointment A-1006, and Appointment A-1012.

### Q28. Which patients are senior patients?

- **Category:** reasoning
- **Intent detected:** `instances` (confidence 0.95)
- **Status:** PASS (0.144 s)
- **Expected facts:** John Miller, Robert Brown, William Thomas, inferred

**Agent answer:**

> **Senior Patient** individuals (3) — inferred by the HermiT reasoner:
> - Robert Brown (`p003`)
> - John Miller (`p001`)
> - William Thomas (`p009`)

### Q29. Is John Miller a senior patient?

- **Category:** reasoning
- **Intent detected:** `yes_no` (confidence 0.98)
- **Status:** PASS (0.137 s)
- **Expected facts:** Yes, Senior Patient

**Agent answer:**

> **Yes.** John Miller is a Senior Patient.

### Q30. Who is the oldest patient?

- **Category:** superlative
- **Intent detected:** `superlative` (confidence 1.00)
- **Status:** PASS (0.149 s)
- **Expected facts:** William Thomas, 80

**Agent answer:**

> **William Thomas** is the oldest with value **80**.

**SPARQL used:**

```sparql
SELECT ?x ?v WHERE { ?x rdf:type/rdfs:subClassOf* h:Patient ; h:age ?v } ORDER BY DESC(?v) LIMIT 1
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p009 http://example.org/hospital#age 80
```

### Q31. What is the relationship between John Miller and Dr. Alice Chen?

- **Category:** relationship path
- **Intent detected:** `relationship_between` (confidence 0.95)
- **Status:** PASS (0.006 s)
- **Expected facts:** relationship, treated by

**Agent answer:**

> **Relationship path:** John Miller -> [treated by] Dr. Alice Chen
> 
> John Miller and Dr. Alice Chen are connected through 1 ontology relationship(s).

### Q32. Which diseases affect the respiratory system?

- **Category:** attribute
- **Intent detected:** `diseases_by_system` (confidence 0.98)
- **Status:** PASS (0.118 s)
- **Expected facts:** Asthma, Pneumonia, COPD, Influenza

**Agent answer:**

> Diseases affecting the **Respiratory System**: Asthma, COPD, Influenza, and Pneumonia.

**SPARQL used:**

```sparql
SELECT ?d WHERE { ?d h:hasAffectedSystem h:RespiratorySystem }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#Pneumonia http://example.org/hospital#hasAffectedSystem http://example.org/hospital#RespiratorySystem
http://example.org/hospital#Influenza http://example.org/hospital#hasAffectedSystem http://example.org/hospital#RespiratorySystem
http://example.org/hospital#Asthma http://example.org/hospital#hasAffectedSystem http://example.org/hospital#RespiratorySystem
http://example.org/hospital#COPD http://example.org/hospital#hasAffectedSystem http://example.org/hospital#RespiratorySystem
```

### Q33. Which patients are allergic to Aspirin?

- **Category:** relationship
- **Intent detected:** `patients_allergic` (confidence 0.98)
- **Status:** PASS (0.093 s)
- **Expected facts:** Sophia Martinez

**Agent answer:**

> Patients allergic to **Aspirin**: Sophia Martinez.

**SPARQL used:**

```sparql
SELECT ?p WHERE { ?p h:allergicTo h:Aspirin }
```

**Evidence triples (first 6):**

```
http://example.org/hospital#p006 http://example.org/hospital#allergicTo http://example.org/hospital#Aspirin
```

### Q34. Which patients have more than one disease?

- **Category:** aggregation
- **Intent detected:** `comorbidity_count` (confidence 0.98)
- **Status:** PASS (0.103 s)
- **Expected facts:** John Miller, Robert Brown, William Thomas

**Agent answer:**

> Patients with **2 or more** distinct recorded diseases: Robert Brown (2), John Miller (2), and William Thomas (2).

**SPARQL used:**

```sparql
SELECT ?p (COUNT(DISTINCT ?d) AS ?n) WHERE { ?p h:diagnosedWith ?d } GROUP BY ?p HAVING (COUNT(DISTINCT ?d) >= 2)
```

### Q35. List all object properties.

- **Category:** schema
- **Intent detected:** `list_object_properties` (confidence 1.00)
- **Status:** PASS (0.14 s)
- **Expected facts:** Object properties, diagnosed with, works in, interacts with

**Agent answer:**

> **Object properties**
> - **affects patient**: Disease -> Patient
> - **affiliated with**: Doctor -> Hospital
> - **allergic to**: Patient -> Medication
> - **causes**: Disease -> Symptom
> - **covers disease**: Insurance Plan -> Disease
> - **diagnosed with**: Patient -> Disease
> - **for patient**: Appointment -> Patient
> - **has affected system**: Disease -> Body System
> - **has appointment**: Patient -> Appointment
> - **has insurance**: Patient -> Insurance Plan
> - **has medical record**: Patient -> Medical Record
> - **has part**: - -> -
> - **has prescription**: Medical Record -> Medication
> - **has scheduled appointment**: Doctor -> Appointment
> - **has symptom**: Patient -> Symptom
> - **head of**: Doctor -> Department
> - **indicated by**: Symptom -> Disease
> - **interacts with**: Medication -> Medication
> - **part of**: - -> -
> - **prescribed by**: Medication -> Doctor
> - **prescribed for**: Medication -> Patient
> - **records diagnosis**: Medical Record -> Disease
> - **treated by**: Patient -> Doctor
> - **treated with**: Disease -> Treatment
> - **treats disease**: Healthcare Worker -> Disease
> - **treats patient**: Doctor -> Patient
> - **with doctor**: Appointment -> Doctor
> - **works in**: Healthcare Worker -> Department

### Q36. What is the capital of France?

- **Category:** unknown
- **Intent detected:** `unknown` (confidence 0.00)
- **Status:** PASS (0.007 s)
- **Expected facts:** could not find an answer

**Agent answer:**

> I could not find an answer to **"What is the capital of France?"** in the hospital ontology.
> 
> I only answer from facts stored in `hospital_ontology.owl`; I do not guess or invent information. Try asking about patients, doctors, diseases, symptoms, medications, departments, appointments or insurance plans (or type `help`).

### Q37. Who is the CEO of Google?

- **Category:** unknown
- **Intent detected:** `unknown` (confidence 0.00)
- **Status:** PASS (0.103 s)
- **Expected facts:** could not find an answer

**Agent answer:**

> I could not find an answer to **"Who is the CEO of Google?"** in the hospital ontology.
> 
> I only answer from facts stored in `hospital_ontology.owl`; I do not guess or invent information. Try asking about patients, doctors, diseases, symptoms, medications, departments, appointments or insurance plans (or type `help`).

### Q38. What is the population of Springfield?

- **Category:** unknown
- **Intent detected:** `unknown` (confidence 0.00)
- **Status:** PASS (0.081 s)
- **Expected facts:** could not find an answer

**Agent answer:**

> I could not find an answer to **"What is the population of Springfield?"** in the hospital ontology.
> 
> I only answer from facts stored in `hospital_ontology.owl`; I do not guess or invent information. Try asking about patients, doctors, diseases, symptoms, medications, departments, appointments or insurance plans (or type `help`).
