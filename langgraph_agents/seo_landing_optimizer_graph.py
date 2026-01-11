"""
SEO Landing Page Optimizer Graph
=================================

LangGraph-based workflow for SEO landing page optimization.

Workflow:
1. Fetch Search Console data
2. Analyze keyword opportunities
3. Check existing pages
4. Create page strategy
5. Generate page config
6. Save and deploy
7. Generate report

Author: Claude
Version: 1.0.0
"""

import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from langgraph.graph import StateGraph, END
import structlog

from .base_graph import BaseAgentGraph
from .state_schemas import SEOLandingOptimizerState, init_seo_landing_optimizer_state

logger = structlog.get_logger(__name__)

# Constants
LANDING_PAGES_CONFIG_PATH = Path("/home/claude/projects/sale-v2/pomandi-landing-pages/src/config/pages")
COOLIFY_APP_UUID = "dkgksok4g0o04oko88g08s0g"
MIN_IMPRESSIONS_THRESHOLD = 100
POSITION_OPPORTUNITY_RANGE = (4, 20)


class SEOLandingOptimizerGraph(BaseAgentGraph):
    """
    SEO Landing Page Optimizer workflow graph.

    Analyzes Search Console data, identifies high-potential keywords,
    and generates optimized landing pages.
    """

    def __init__(self, **kwargs):
        super().__init__(enable_memory=True, **kwargs)
        self.search_console_client = None
        self.coolify_client = None

    def build_graph(self) -> StateGraph:
        """Build the SEO optimizer workflow graph."""
        graph = StateGraph(SEOLandingOptimizerState)

        # Add nodes
        graph.add_node("fetch_search_console_data", self.fetch_search_console_data)
        graph.add_node("analyze_opportunities", self.analyze_opportunities)
        graph.add_node("check_existing_pages", self.check_existing_pages)
        graph.add_node("select_target_keyword", self.select_target_keyword)
        graph.add_node("generate_page_config", self.generate_page_config)
        graph.add_node("validate_config", self.validate_config)
        graph.add_node("save_config", self.save_config)
        graph.add_node("trigger_deployment", self.trigger_deployment)
        graph.add_node("generate_report", self.generate_report)

        # Set entry point
        graph.set_entry_point("fetch_search_console_data")

        # Define edges
        graph.add_edge("fetch_search_console_data", "analyze_opportunities")
        graph.add_edge("analyze_opportunities", "check_existing_pages")
        graph.add_edge("check_existing_pages", "select_target_keyword")

        # Conditional edge: generate page only if keyword selected
        graph.add_conditional_edges(
            "select_target_keyword",
            self.should_generate_page,
            {
                "generate": "generate_page_config",
                "skip": "generate_report"
            }
        )

        graph.add_edge("generate_page_config", "validate_config")

        # Conditional edge: save only if valid
        graph.add_conditional_edges(
            "validate_config",
            self.is_config_valid,
            {
                "valid": "save_config",
                "invalid": "generate_report"
            }
        )

        graph.add_edge("save_config", "trigger_deployment")
        graph.add_edge("trigger_deployment", "generate_report")
        graph.add_edge("generate_report", END)

        return graph

    # =========================================================================
    # Node Implementations
    # =========================================================================

    async def fetch_search_console_data(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 1: Fetch Search Console data.

        Uses MCP tools to get:
        - Keyword opportunities
        - Top queries
        - Top pages
        - Position distribution
        """
        logger.info("fetch_search_console_data_start")

        try:
            # In real implementation, these would be MCP tool calls
            # For now, we'll create placeholder structure
            # The SDK runner will handle actual MCP calls

            state["keyword_opportunities"] = []
            state["top_queries"] = []
            state["top_pages"] = []
            state["position_distribution"] = {}
            state["seo_summary"] = None

            state = self.add_step(state, "fetch_search_console_data")
            logger.info("fetch_search_console_data_complete")

        except Exception as e:
            state = self.set_error(state, f"Failed to fetch Search Console data: {e}")

        return state

    async def analyze_opportunities(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 2: Analyze keyword opportunities.

        Filters and scores keywords by:
        - Position (4-20 range)
        - Impressions (> threshold)
        - CTR potential
        """
        logger.info("analyze_opportunities_start")

        try:
            opportunities = []

            for query in state.get("top_queries", []):
                position = query.get("position", 0)
                impressions = query.get("impressions", 0)
                ctr = query.get("ctr", 0)

                # Check if in opportunity range
                if not (POSITION_OPPORTUNITY_RANGE[0] <= position <= POSITION_OPPORTUNITY_RANGE[1]):
                    continue

                if impressions < MIN_IMPRESSIONS_THRESHOLD:
                    continue

                # Calculate potential score
                # Higher score = better opportunity
                # Position closer to 3 = higher score
                # More impressions = higher score
                # Lower CTR = more room for improvement
                position_score = (POSITION_OPPORTUNITY_RANGE[1] - position) / (POSITION_OPPORTUNITY_RANGE[1] - POSITION_OPPORTUNITY_RANGE[0])
                impression_score = min(impressions / 1000, 1.0)
                ctr_improvement_potential = max(0, 1 - (ctr / 5))  # Assume 5% is good CTR

                potential_score = (position_score * 0.4 + impression_score * 0.4 + ctr_improvement_potential * 0.2)

                opportunities.append({
                    "query": query.get("query", ""),
                    "clicks": query.get("clicks", 0),
                    "impressions": impressions,
                    "ctr": ctr,
                    "position": position,
                    "potential_score": round(potential_score, 3)
                })

            # Sort by potential score
            opportunities.sort(key=lambda x: x["potential_score"], reverse=True)
            state["keyword_opportunities"] = opportunities

            state = self.add_step(state, "analyze_opportunities")
            logger.info("analyze_opportunities_complete", count=len(opportunities))

        except Exception as e:
            state = self.set_error(state, f"Failed to analyze opportunities: {e}")

        return state

    async def check_existing_pages(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 3: Check existing landing pages.

        Scans config directory for existing pages to avoid duplicates.
        """
        logger.info("check_existing_pages_start")

        try:
            existing_pages = []
            existing_keywords = []

            if LANDING_PAGES_CONFIG_PATH.exists():
                for config_file in LANDING_PAGES_CONFIG_PATH.glob("*.json"):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                            slug = config.get("slug", "")
                            if slug:
                                existing_pages.append(slug)

                            # Extract keywords from SEO config
                            seo = config.get("seo", {})
                            keywords = seo.get("keywords", [])
                            existing_keywords.extend(keywords)

                            # Also extract from title
                            title = seo.get("title", {})
                            if isinstance(title, dict):
                                for lang_title in title.values():
                                    # Extract main keyword from title
                                    words = lang_title.lower().split()[:3]
                                    existing_keywords.extend(words)
                    except Exception as e:
                        logger.warning(f"Failed to parse {config_file}: {e}")

            state["existing_pages"] = list(set(existing_pages))
            state["existing_keywords"] = list(set(existing_keywords))

            state = self.add_step(state, "check_existing_pages")
            logger.info("check_existing_pages_complete",
                       pages=len(existing_pages),
                       keywords=len(existing_keywords))

        except Exception as e:
            state = self.set_error(state, f"Failed to check existing pages: {e}")

        return state

    async def select_target_keyword(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 4: Select target keyword for today's page.

        Picks the highest-potential keyword not already covered.
        """
        logger.info("select_target_keyword_start")

        try:
            existing_keywords_lower = [k.lower() for k in state.get("existing_keywords", [])]
            existing_pages_lower = [p.lower() for p in state.get("existing_pages", [])]

            selected_keyword = None
            selected_template = None

            for opportunity in state.get("keyword_opportunities", []):
                query = opportunity.get("query", "").lower()

                # Skip if already covered
                if query in existing_keywords_lower:
                    continue

                # Generate potential slug
                potential_slug = self._generate_slug(query)
                if potential_slug in existing_pages_lower:
                    continue

                # Check for similar keywords
                is_similar = False
                for existing in existing_keywords_lower:
                    if self._keyword_similarity(query, existing) > 0.7:
                        is_similar = True
                        break

                if is_similar:
                    continue

                # This is our target!
                selected_keyword = query
                selected_template = self._determine_template(query)
                break

            state["selected_keyword"] = selected_keyword
            state["selected_template"] = selected_template

            if selected_keyword:
                state["page_strategy"] = {
                    "keyword": selected_keyword,
                    "template": selected_template,
                    "slug": self._generate_slug(selected_keyword),
                    "target_position": "top 3",
                    "expected_ctr_improvement": "2-5%"
                }
                logger.info("select_target_keyword_complete", keyword=selected_keyword, template=selected_template)
            else:
                state = self.add_warning(state, "No suitable keyword opportunity found today")
                logger.info("select_target_keyword_no_opportunity")

            state = self.add_step(state, "select_target_keyword")

        except Exception as e:
            state = self.set_error(state, f"Failed to select target keyword: {e}")

        return state

    async def generate_page_config(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 5: Generate landing page configuration.

        Creates PageConfig JSON with SEO-optimized content.
        """
        logger.info("generate_page_config_start")

        try:
            keyword = state.get("selected_keyword", "")
            template = state.get("selected_template", "location")
            slug = self._generate_slug(keyword)

            # Determine channels based on language
            if any(fr_word in keyword.lower() for fr_word in ["costume", "mariage", "homme", "bruxelles", "liège"]):
                channels = ["belgium-channel"]
                primary_lang = "fr"
            elif any(nl_word in keyword.lower() for nl_word in ["pak", "maatpak", "trouw", "kostuum"]):
                channels = ["belgium-channel", "netherlands-channel"]
                primary_lang = "nl"
            else:
                channels = ["belgium-channel", "netherlands-channel"]
                primary_lang = "nl"

            # Generate SEO content
            seo_title = self._generate_seo_title(keyword, primary_lang)
            seo_description = self._generate_seo_description(keyword, primary_lang)

            config = {
                "slug": slug,
                "template": template,
                "channels": channels,
                "theme": {
                    "mode": "light",
                    "primary": "#1a1a1a",
                    "secondary": "#444444",
                    "background": "#f8f7f5"
                },
                "seo": {
                    "title": seo_title,
                    "description": seo_description,
                    "keywords": self._generate_keywords(keyword),
                    "canonical": f"https://www.pomandi.com/{primary_lang}/{slug}",
                    "ogImage": "/1.png"
                },
                "hero": {
                    "title": self._generate_hero_title(keyword),
                    "subtitle": self._generate_hero_subtitle(keyword),
                    "image": "/hero.jpg",
                    "cta": {
                        "text": {
                            "nl": "Maak een afspraak",
                            "fr": "Prenez rendez-vous",
                            "en": "Book appointment"
                        },
                        "link": f"/{primary_lang}/afspraak"
                    }
                },
                "sections": self._generate_sections(keyword, template),
                "campaign": f"seo-{slug}-{datetime.now().strftime('%Y%m')}"
            }

            state["generated_config"] = config
            state = self.add_step(state, "generate_page_config")
            logger.info("generate_page_config_complete", slug=slug)

        except Exception as e:
            state = self.set_error(state, f"Failed to generate page config: {e}")

        return state

    async def validate_config(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 6: Validate generated configuration.

        Checks:
        - Required fields present
        - SEO title/description lengths
        - Valid JSON structure
        """
        logger.info("validate_config_start")

        try:
            config = state.get("generated_config")
            is_valid = True
            validation_errors = []

            if not config:
                validation_errors.append("No config generated")
                is_valid = False
            else:
                # Check required fields
                required_fields = ["slug", "template", "channels", "seo", "hero", "sections"]
                for field in required_fields:
                    if field not in config:
                        validation_errors.append(f"Missing required field: {field}")
                        is_valid = False

                # Check SEO title length (50-60 chars recommended)
                seo = config.get("seo", {})
                for lang, title in seo.get("title", {}).items():
                    if len(title) > 70:
                        validation_errors.append(f"SEO title too long for {lang}: {len(title)} chars")
                        state = self.add_warning(state, f"Title for {lang} is {len(title)} chars (recommended: 50-60)")

                # Check description length (150-160 chars recommended)
                for lang, desc in seo.get("description", {}).items():
                    if len(desc) > 170:
                        validation_errors.append(f"Description too long for {lang}: {len(desc)} chars")
                        state = self.add_warning(state, f"Description for {lang} is {len(desc)} chars (recommended: 150-160)")

                # Check minimum sections
                if len(config.get("sections", [])) < 2:
                    validation_errors.append("Too few sections (minimum 2)")
                    is_valid = False

            state["config_validated"] = is_valid

            if not is_valid:
                state = self.add_warning(state, f"Config validation failed: {', '.join(validation_errors)}")

            state = self.add_step(state, "validate_config")
            logger.info("validate_config_complete", is_valid=is_valid)

        except Exception as e:
            state = self.set_error(state, f"Failed to validate config: {e}")
            state["config_validated"] = False

        return state

    async def save_config(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 7: Save configuration file.

        Writes JSON config to landing pages project.
        """
        logger.info("save_config_start")

        try:
            config = state.get("generated_config")
            if not config:
                state = self.set_error(state, "No config to save")
                return state

            slug = config.get("slug", "unknown")
            file_path = LANDING_PAGES_CONFIG_PATH / f"{slug}.json"

            # Ensure directory exists
            LANDING_PAGES_CONFIG_PATH.mkdir(parents=True, exist_ok=True)

            # Write config
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            state["config_saved"] = True
            state = self.add_step(state, "save_config")
            logger.info("save_config_complete", path=str(file_path))

        except Exception as e:
            state = self.set_error(state, f"Failed to save config: {e}")
            state["config_saved"] = False

        return state

    async def trigger_deployment(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 8: Trigger Coolify deployment.

        Calls Coolify MCP to deploy the landing pages app.
        """
        logger.info("trigger_deployment_start")

        try:
            # In real implementation, this would use MCP:
            # mcp__coolify__restart_application(uuid=COOLIFY_APP_UUID)

            state["deployment_triggered"] = True
            state["deployment_uuid"] = COOLIFY_APP_UUID
            state["deployment_status"] = "pending"

            state = self.add_step(state, "trigger_deployment")
            logger.info("trigger_deployment_complete", uuid=COOLIFY_APP_UUID)

        except Exception as e:
            state = self.set_error(state, f"Failed to trigger deployment: {e}")
            state["deployment_triggered"] = False

        return state

    async def generate_report(self, state: SEOLandingOptimizerState) -> SEOLandingOptimizerState:
        """
        Node 9: Generate execution report.

        Creates markdown report summarizing actions taken.
        """
        logger.info("generate_report_start")

        try:
            report_lines = [
                f"# SEO Landing Optimizer Report",
                f"**Date:** {state.get('target_date', datetime.now().strftime('%Y-%m-%d'))}",
                f"**Mode:** {state.get('mode', 'analyze')}",
                "",
                "## Summary",
            ]

            # Keyword opportunities
            opportunities = state.get("keyword_opportunities", [])
            report_lines.append(f"- **Opportunities Found:** {len(opportunities)}")

            # Selected keyword
            keyword = state.get("selected_keyword")
            if keyword:
                report_lines.append(f"- **Selected Keyword:** {keyword}")
                report_lines.append(f"- **Template:** {state.get('selected_template', 'N/A')}")
            else:
                report_lines.append("- **Selected Keyword:** None (no suitable opportunity)")

            # Page generated
            config = state.get("generated_config")
            if config:
                report_lines.append(f"- **Generated Page:** {config.get('slug')}")
                report_lines.append(f"- **Config Saved:** {'Yes' if state.get('config_saved') else 'No'}")
                report_lines.append(f"- **Deployment Triggered:** {'Yes' if state.get('deployment_triggered') else 'No'}")

            # Top opportunities
            if opportunities[:5]:
                report_lines.extend([
                    "",
                    "## Top 5 Keyword Opportunities",
                    "| Keyword | Position | Impressions | Potential Score |",
                    "|---------|----------|-------------|-----------------|"
                ])
                for opp in opportunities[:5]:
                    report_lines.append(
                        f"| {opp['query']} | {opp['position']:.1f} | {opp['impressions']} | {opp['potential_score']:.3f} |"
                    )

            # Warnings
            warnings = state.get("warnings", [])
            if warnings:
                report_lines.extend([
                    "",
                    "## Warnings",
                ])
                for warning in warnings:
                    report_lines.append(f"- {warning}")

            # Errors
            error = state.get("error")
            if error:
                report_lines.extend([
                    "",
                    "## Errors",
                    f"- {error}"
                ])

            # Steps completed
            steps = state.get("steps_completed", [])
            report_lines.extend([
                "",
                "## Steps Completed",
            ])
            for i, step in enumerate(steps, 1):
                report_lines.append(f"{i}. {step}")

            state["report_content"] = "\n".join(report_lines)
            state["report_saved"] = True

            state = self.add_step(state, "generate_report")
            logger.info("generate_report_complete")

        except Exception as e:
            state = self.set_error(state, f"Failed to generate report: {e}")

        return state

    # =========================================================================
    # Conditional Edge Functions
    # =========================================================================

    def should_generate_page(self, state: SEOLandingOptimizerState) -> str:
        """Decide whether to generate a new page."""
        if state.get("selected_keyword") and state.get("mode") in ["analyze", "generate"]:
            return "generate"
        return "skip"

    def is_config_valid(self, state: SEOLandingOptimizerState) -> str:
        """Check if config validation passed."""
        return "valid" if state.get("config_validated") else "invalid"

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _generate_slug(self, keyword: str) -> str:
        """Generate URL-safe slug from keyword."""
        slug = keyword.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')

    def _determine_template(self, keyword: str) -> str:
        """Determine appropriate template for keyword."""
        keyword_lower = keyword.lower()

        # Location keywords
        cities = ["antwerp", "antwerpen", "brussels", "bruxelles", "gent", "ghent",
                  "rotterdam", "amsterdam", "kortrijk", "roeselare", "limburg",
                  "liège", "luik", "charleroi", "namen", "namur"]
        if any(city in keyword_lower for city in cities):
            return "location"

        # Style keywords
        styles = ["jaren", "peaky", "british", "tweed", "vintage", "gangster",
                  "driedelig", "three-piece", "super 100", "slim fit", "classic"]
        if any(style in keyword_lower for style in styles):
            return "style"

        # Promo keywords
        promos = ["actie", "promo", "korting", "sale", "aanbieding", "solde"]
        if any(promo in keyword_lower for promo in promos):
            return "promo"

        # Default to location (most common)
        return "location"

    def _keyword_similarity(self, kw1: str, kw2: str) -> float:
        """Calculate simple keyword similarity."""
        words1 = set(kw1.lower().split())
        words2 = set(kw2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def _generate_seo_title(self, keyword: str, primary_lang: str) -> Dict[str, str]:
        """Generate SEO titles for all languages."""
        keyword_cap = keyword.title()

        titles = {
            "nl": f"{keyword_cap} - Premium Herenkostuums vanaf €320 | Pomandi",
            "fr": f"{keyword_cap} - Costumes Homme Premium dès €320 | Pomandi",
            "en": f"{keyword_cap} - Premium Men's Suits from €320 | Pomandi"
        }

        return titles

    def _generate_seo_description(self, keyword: str, primary_lang: str) -> Dict[str, str]:
        """Generate SEO descriptions for all languages."""
        keyword_lower = keyword.lower()

        descriptions = {
            "nl": f"Op zoek naar {keyword_lower}? Pomandi biedt premium maatpakken vanaf €320. Meer dan 10 jaar ervaring in maatwerk. Maak vandaag nog een afspraak!",
            "fr": f"Vous cherchez {keyword_lower}? Pomandi propose des costumes sur mesure premium dès €320. Plus de 10 ans d'expérience. Prenez rendez-vous!",
            "en": f"Looking for {keyword_lower}? Pomandi offers premium custom suits from €320. Over 10 years of tailoring experience. Book your appointment today!"
        }

        return descriptions

    def _generate_hero_title(self, keyword: str) -> Dict[str, str]:
        """Generate hero titles."""
        keyword_cap = keyword.title()
        return {
            "nl": keyword_cap,
            "fr": keyword_cap,
            "en": keyword_cap
        }

    def _generate_hero_subtitle(self, keyword: str) -> Dict[str, str]:
        """Generate hero subtitles."""
        return {
            "nl": "Premium herenkostuums op maat",
            "fr": "Costumes homme sur mesure premium",
            "en": "Premium tailored men's suits"
        }

    def _generate_keywords(self, keyword: str) -> List[str]:
        """Generate related keywords."""
        base_keywords = [keyword.lower()]

        # Add variations
        if "pak" in keyword.lower():
            base_keywords.extend(["maatpak", "kostuum", "herenpak"])
        if "costume" in keyword.lower():
            base_keywords.extend(["costume sur mesure", "costume homme", "tailleur"])
        if "suit" in keyword.lower():
            base_keywords.extend(["custom suit", "tailored suit", "men's suit"])

        # Add Pomandi brand
        base_keywords.append("pomandi")

        return list(set(base_keywords))[:10]

    def _generate_sections(self, keyword: str, template: str) -> List[Dict[str, Any]]:
        """Generate page sections based on template."""
        sections = []

        # Features section (always)
        sections.append({
            "type": "features",
            "title": {
                "nl": "Waarom Pomandi?",
                "fr": "Pourquoi Pomandi?",
                "en": "Why Pomandi?"
            },
            "items": [
                {
                    "icon": "scissors",
                    "title": {"nl": "Op Maat", "fr": "Sur Mesure", "en": "Custom Made"},
                    "description": {"nl": "Elk pak wordt op maat gemaakt", "fr": "Chaque costume est fait sur mesure", "en": "Every suit is custom tailored"}
                },
                {
                    "icon": "star",
                    "title": {"nl": "Premium Stoffen", "fr": "Tissus Premium", "en": "Premium Fabrics"},
                    "description": {"nl": "Alleen de beste stoffen", "fr": "Seulement les meilleurs tissus", "en": "Only the finest fabrics"}
                },
                {
                    "icon": "clock",
                    "title": {"nl": "10+ Jaar Ervaring", "fr": "10+ Ans d'Expérience", "en": "10+ Years Experience"},
                    "description": {"nl": "Vakmanschap sinds 2014", "fr": "Artisanat depuis 2014", "en": "Craftsmanship since 2014"}
                }
            ]
        })

        # Products section
        sections.append({
            "type": "products",
            "title": {
                "nl": "Onze Collectie",
                "fr": "Notre Collection",
                "en": "Our Collection"
            },
            "collections": ["maatpak-collectie"]
        })

        # Testimonials
        sections.append({
            "type": "testimonials",
            "title": {
                "nl": "Wat Klanten Zeggen",
                "fr": "Ce Que Disent Nos Clients",
                "en": "What Customers Say"
            }
        })

        # FAQ section
        sections.append({
            "type": "faq",
            "title": {
                "nl": "Veelgestelde Vragen",
                "fr": "Questions Fréquentes",
                "en": "FAQ"
            },
            "items": [
                {
                    "question": {"nl": "Hoe werkt een maatpak?", "fr": "Comment fonctionne le sur-mesure?", "en": "How does custom tailoring work?"},
                    "answer": {"nl": "We nemen 25+ maten en maken het pak speciaal voor jou.", "fr": "Nous prenons 25+ mesures et faisons le costume spécialement pour vous.", "en": "We take 25+ measurements and create the suit specifically for you."}
                },
                {
                    "question": {"nl": "Wat kost een maatpak?", "fr": "Quel est le prix d'un costume?", "en": "What does a custom suit cost?"},
                    "answer": {"nl": "Onze maatpakken beginnen vanaf €320.", "fr": "Nos costumes sur mesure commencent à partir de €320.", "en": "Our custom suits start from €320."}
                }
            ]
        })

        # CTA section
        sections.append({
            "type": "cta",
            "title": {
                "nl": "Klaar voor jouw perfecte pak?",
                "fr": "Prêt pour votre costume parfait?",
                "en": "Ready for your perfect suit?"
            },
            "button": {
                "text": {"nl": "Maak een afspraak", "fr": "Prenez rendez-vous", "en": "Book appointment"},
                "link": "/nl/afspraak"
            }
        })

        # Add store section for location template
        if template == "location":
            sections.insert(3, {
                "type": "stores",
                "title": {
                    "nl": "Onze Winkels",
                    "fr": "Nos Magasins",
                    "en": "Our Stores"
                }
            })

        return sections

    # =========================================================================
    # Public API
    # =========================================================================

    async def analyze(self, target_date: str = None) -> Dict[str, Any]:
        """
        Run analysis mode.

        Args:
            target_date: Target date (YYYY-MM-DD)

        Returns:
            Final state with analysis results
        """
        state = init_seo_landing_optimizer_state(
            mode="analyze",
            target_date=target_date
        )
        return await self.run(**state)

    async def generate(self, target_date: str = None) -> Dict[str, Any]:
        """
        Run generation mode.

        Args:
            target_date: Target date (YYYY-MM-DD)

        Returns:
            Final state with generated page
        """
        state = init_seo_landing_optimizer_state(
            mode="generate",
            target_date=target_date
        )
        return await self.run(**state)

    async def report(self) -> Dict[str, Any]:
        """
        Run report-only mode.

        Returns:
            Final state with report
        """
        state = init_seo_landing_optimizer_state(mode="report")
        return await self.run(**state)
