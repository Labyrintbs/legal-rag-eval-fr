# Spot check: Code du travail

20 articles drawn with a fixed seed, plus edge cases. Open each URL on legifrance.gouv.fr and compare number, in-force date, text and place in the code with the data. The site shows today's version, the data is the 2025-07-13 snapshot.

## Checked (14 of 20)

| Article | URL | Result |
|---|---|---|
| R3232-8 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000043128608 | OK: number, date (2021-02-13), text and all 6 path levels match the site. |
| L4162-4 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000036262858 | OK: number, date (2019-01-01) and text match. Data path has 7 levels, site 5: two older titles ("Titre VI : ...pénibilité", "Chapitre II : Compte personnel de prévention de la pénibilité") appear before the current ones. |
| L3132-25-3 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000035653129 | URL, status (in force since 2018-01-01) and path match the site; the data path has one extra level ("Paragraphe 3 : Dérogations temporaires...") that the site does not show. Article number and text not visible in the screenshot. |
| L6362-12 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006904464 | OK: number, date (2008-05-01) and text match. Data path has 8 levels, site 6: older "Livre III : ...continue" and "Titre VI : ...continue" appear before the current titles. |
| R5123-8 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000018527022 | OK: number, date (2008-05-01), text and all 6 levels match (data has a double space in one title). |
| L2262-8 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006901817 | OK: number, date (2008-05-01), text and all 6 levels match. |
| R4451-6 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000037024991 | OK: number, date (2018-07-01) and text match. Data path 12 levels, site 7: each of Titre V, Chapitre Ier, Section 3, Sous-section 1 appears 2-3 times with different titles; the site shows the last one of each. |
| D6331-71 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000038023456 | OK: number, date (2019-01-01) and text start match. Data path 8 levels, site 7: "Section 4" appears twice, the site shows the second (longer) one. Livre III is "...formation professionnelle continue" on the site too (regulatory part). |
| D4626-5 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000045677256 | OK: number, date (2022-04-28) and text match. Data path 9 levels, site 6: "Titre II" appears 3 times, the site shows the last ("Services de prévention et de santé au travail"). |
| R7524-1 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000037563341 | OK: number, date (2018-11-07), text and path (6 levels, 5 after collapsing) match. Quotes are curly with inner spaces in the data, straight on the site. |
| R4641-15 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000044804685 | OK: date (2022-03-31) and path match (data 12 levels, site 8). Text not visible in the screenshot. |
| L7342-11 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000039678041 | OK: number, date (2019-12-27), text and path (data 8 levels, site 6) match. |
| R5132-21 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000018526800 | OK: date (2008-05-01) and path match (7 levels). Text not visible in the screenshot. |
| D1441-24-2 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000037481360 | OK: date (2018-10-10) and path match (data 10 levels, site 7). Text not visible in the screenshot. |

## Still to check (6 of 20)

| Article | URL | Section path (last level) | Body start | Result |
|---|---|---|---|---|
| L2363-12 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000018050413 | Section 3 : Dispositions applicables aux sociétés coopératives européennes non soumises initialement à la constitution du groupe spécial de négociation | Dans le cas de la société coopérative européenne mentionnée à l'article L. 2363- | |
| D5132-10-2 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000029775713 | Sous-section 3 : Périodes de mise en situation en milieu professionnel. | Chaque période de mise en situation en milieu professionnel prescrite, en accord | |
| L2362-9 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000018050480 | Sous-section 3 : Fonctionnement | Les dispositions des articles L. 2352-14 et L. 2352-15 relatives à la protection | |
| L3123-9 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033020058 | Paragraphe 5 : Durée minimale de travail et heures complémentaires | Les heures complémentaires ne peuvent avoir pour effet de porter la durée de tra | |
| L5426-8-3 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000048600556 | Section 4 : Répétition des prestations indues. | L'opérateur France Travail est autorisé à différer ou à abandonner la mise en re | |
| R5324-1 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000018525260 | Chapitre IV : Contrôle | Lorsque des manquements à la réglementation ont été constatés dans les condition | |

## Edge cases (not in the seeded sample)

| Article | URL | What to look at | Result |
|---|---|---|---|
| L1237-1 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006901174 | Resignation notice; the path used in our example header | |
| L1232-3 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006901001 | Same body as L1233-12 | |
| L1233-12 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000006901024 | Same body as L1232-3; its path says dismissal (licenciement) | |
| R*3231-4 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000018552958 | Number with a star | |
| L1251-33-1 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000048600683 | Number had a leading space in the source | |
| L2152-1 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000033023399 | Path contains a carriage return in the source | |
| L6123-5 | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000048700924 | Long article, split into several chunks | |
| Annexe I | https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000040477365 | Annex whose text is only a link to a PDF | |
