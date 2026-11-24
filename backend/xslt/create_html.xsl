<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet 
  version="3.0"
  xmlns:tei="http://www.tei-c.org/ns/1.0" 
  xmlns:hei="https://digi.ub.uni-heidelberg.de/schema/tei/heiEDITIONS"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  >

<!-- 
    
-->  
     
  <!-- indent="no": the html output method defaults to indent="yes", which
       auto-inserts whitespace around elements the serializer doesn't
       recognize as inline (e.g. TEI's <surplus>, left un-transformed by the
       identity/shallow-copy default below) - splitting words like
       "gerstenkoren" apart with a stray newline. The tree arriving here is
       already whitespace-correct (reduce_markup/whitespaces upstream), so
       nothing should be added at serialization time. -->
  <xsl:output method="html" indent="no"/>

  <!-- Identity template -->
  <xsl:mode on-no-match="shallow-copy" />

  
  
    <xsl:template match="tei:TEI | tei:text | tei:front | tei:lg">
        <div>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="name()"/>
                <xsl:for-each select="@*">
                    <xsl:if test="name() = tokenize('ana rendition')">
                        <xsl:text> </xsl:text>
                        <xsl:value-of select="."/>
                    </xsl:if>
                </xsl:for-each>
            </xsl:attribute>
            <xsl:apply-templates select="node()"/>
        </div>    
    </xsl:template>

    <xsl:template match="tei:lb">
        <span class="tei-lb"/>
    </xsl:template>

    <!-- Synoptic units: the loci of the text, each with its number (or
         label) in the margin and its content beside it.

         The synoptic map decides which elements are loci: the
         heicrit_append_synoptic_links step (heicrit_pipeline.py) marks every
         element it links with @hei:locus. Loci can nest (a <div> holding
         <l>s, a <seg> inside an <l>), so only the innermost ones get a
         content column (the token overlay and lemma selection work on it);
         a locus holding other loci is an outer unit around them (see the
         template after this one). Without a map, or where it links nothing,
         each l/p/titlePart is a unit, as before. -->
    <xsl:template match="*[@hei:locus][not(descendant::*[@hei:locus])]
                         | (tei:l | tei:p | tei:titlePart)[not(ancestor-or-self::*[@hei:locus] or descendant::*[@hei:locus])]">
        <!-- revision_spans (a pipeline step run before this one) marks a
             whole line/paragraph reconstructed from other witnesses - not
             present in this manuscript at all - by setting ana to
             "hc:EditorialAdditionSpan" directly on this element. Surface
             that as a class so the base text column can flag it visually
             (see .synoptic-unit-editorial-addition in styles.css). -->
        <div class="synoptic-unit synoptic-unit-{local-name()}{if (contains(concat(' ', @ana, ' '), ' hc:EditorialAdditionSpan ')) then ' synoptic-unit-editorial-addition' else ''}">
            <xsl:apply-templates select="tei:gap[@corresp]">
                <xsl:with-param name="data-container-id" select="@xml:id"/>
            </xsl:apply-templates>
            <div class="tei-container-n">    
                <xsl:attribute name="data-container-id" select="@xml:id"/>
                <xsl:call-template name="locus-label"/>
            </div>            
            <div class="tei-container-content">
                <xsl:apply-templates select="node() except tei:gap[@corresp]"/>
            </div>
        </div>
    </xsl:template>

    <!-- A locus holding other loci (e.g. a linked <div> around linked
         verses): its margin label, then its content with the inner units
         as usual. Only its own leading gap markers (those the synoptic
         links step put inside it for this locus) belong to its label; gaps
         further in mark units missing between its children and stay in
         place. No content column - the inner units carry the tokens. -->
    <xsl:template match="*[@hei:locus][descendant::*[@hei:locus]]">
        <xsl:variable name="own-gaps" select="tei:gap[@corresp][not(preceding-sibling::*[not(self::tei:gap[@corresp])])]"/>
        <div class="synoptic-unit synoptic-unit-outer synoptic-unit-{local-name()}">
            <xsl:apply-templates select="$own-gaps">
                <xsl:with-param name="data-container-id" select="@xml:id"/>
            </xsl:apply-templates>
            <div class="tei-container-n">
                <xsl:attribute name="data-container-id" select="@xml:id"/>
                <xsl:call-template name="locus-label"/>
            </div>
            <div class="synoptic-unit-outer-body">
                <xsl:apply-templates select="node() except $own-gaps"/>
            </div>
        </div>
    </xsl:template>

    <!-- Margin label of a locus: its @n, else a label for its kind. Keep in
         sync with load_functions.LOCUS_LABELS. -->
    <xsl:template name="locus-label">
        <xsl:choose>
            <xsl:when test="@n"><xsl:value-of select="@n"/></xsl:when>
            <xsl:when test="self::tei:head">Head</xsl:when>
            <xsl:when test="self::tei:label">Label</xsl:when>
            <xsl:when test="self::tei:seg">Seg</xsl:when>
            <xsl:when test="self::tei:s">S</xsl:when>
            <xsl:when test="self::tei:div">Div</xsl:when>
            <xsl:when test="self::tei:p">P</xsl:when>
            <xsl:when test="self::tei:titlePart">Title</xsl:when>
        </xsl:choose>
    </xsl:template>

    <!-- Elements that could be loci but aren't units here (inside a unit,
         or not linked): plain blocks / inline spans, never left as raw TEI
         tags - an HTML <head> inside the page body is dropped by the
         browser. -->
    <xsl:template match="tei:l | tei:p | tei:titlePart | tei:head | tei:label | tei:div">
        <div class="tei-{local-name()}">
            <xsl:apply-templates select="node()"/>
        </div>
    </xsl:template>

    <xsl:template match="tei:s | tei:seg">
        <span class="tei-{local-name()}">
            <xsl:apply-templates select="node()"/>
        </span>
    </xsl:template>

    <xsl:template match="tei:pb | tei:cb">
        <span>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="name()"/>
                <xsl:for-each select="@*">
                    <xsl:if test="name() = ('ana', 'rendition', 'facs', 'n')">
                        <xsl:text> </xsl:text>
                        <xsl:value-of select="name()"/>
                        <xsl:text>-</xsl:text>
                        <xsl:value-of select="."/>
                    </xsl:if>
                </xsl:for-each>
            </xsl:attribute>
        </span>
    </xsl:template>

    <xsl:template match="tei:gap[@corresp]">
        <xsl:param name="data-container-id"/>
        <div>
            <xsl:attribute name="class">tei-gap-synoptic</xsl:attribute>
            <xsl:choose>
                <xsl:when test="$data-container-id">
                    <xsl:attribute name="data-container-id" select="$data-container-id"/>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:if test="@n">
                        <xsl:attribute name="data-container-id" select="@n"/>
                    </xsl:if>
                </xsl:otherwise>
            </xsl:choose>
            <xsl:attribute name="data-link" select="@corresp"/>
            <xsl:text>◎</xsl:text>
            <xsl:if test="not($data-container-id) and @n">
                <div class="tei-gap-synoptic-n">
                    <xsl:value-of select="@n"/>
                </div>
            </xsl:if>
        </div>
    </xsl:template>
    
    <!-- Emended text (a <corr> replacing a <sic>, or <supplied> text),
         marked by reduce_markup.xsl. -->
    <xsl:template match="tei:emph[@rend = 'emendation']">
        <em class="emendation"><xsl:apply-templates select="node()"/></em>
    </xsl:template>

    <xsl:template match="tei:gap[not(@corresp)]">
        <span class="tei-gap">[…]</span>
    </xsl:template>

    
    
  
  
  
</xsl:stylesheet>
