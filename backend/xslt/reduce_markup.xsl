<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet 
  version="3.0"
  xpath-default-namespace="http://www.tei-c.org/ns/1.0" 
  xmlns:hei="https://digi.ub.uni-heidelberg.de/schema/tei/heiEDITIONS"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  >


  <xsl:output method="xml"/>

  <!-- Identity template -->
  <xsl:mode on-no-match="shallow-copy" />

  <xsl:param name="editorial" as="xs:boolean" select="false()"/>
  
    <xsl:template match="w | c | choice | pc | g | hi">
        <xsl:apply-templates select="node()"/>
    </xsl:template>

    <xsl:template match="sic | abbr | am">
        <xsl:choose>
            <xsl:when test="$editorial">
            </xsl:when>
            <xsl:otherwise>
                <xsl:apply-templates select="node()"/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>

    <xsl:template match="corr | expan | ex">
        <xsl:if test="$editorial">
            <xsl:apply-templates select="node()"/>
        </xsl:if>
    </xsl:template>

    <!-- The base text column always shows the regularized reading, never the
         diplomatic <orig> - independent of $editorial, since this pipeline
         only ever renders the base text (see backend/routes.py's
         resolve_text_file_from_project). Among a <choice>'s <reg> siblings:
         with only one <reg>, use it regardless of @ana; with more than one,
         use specifically the hc:StandardMHGRegularization one. -->
    <xsl:template match="orig"/>

    <!-- Editorially flagged extra/erroneous text (the mirror of <supplied>)
         is likewise dropped from the always-regularized base text column. -->
    <xsl:template match="surplus"/>

    <xsl:template match="reg">
        <xsl:if test="count(../reg) = 1 or @ana = 'hc:StandardMHGRegularization'">
            <xsl:apply-templates select="node()"/>
        </xsl:if>
    </xsl:template>

    <!-- Word/punctuation spacing in the source is carried entirely by <c>
         elements (typically a single space) or by a <reg> whose ENTIRE
         content is a space (a regularization-only word break, e.g.
         <choice><orig/><reg> </reg></choice>) - any other whitespace-only
         text node is pretty-printing indentation, not intended spacing.
         This includes the padding text inside a <reg> that wraps a <pc>
         (e.g. <reg>\n  <pc>.</pc>\n</reg> - a <w> followed by that should
         render with no space before the punctuation), which is why the
         <reg> exemption below requires it to have no element children.
         Suppress those; a <c>'s or space-only <reg>'s own whitespace content
         passes through via the text() template below unchanged. -->
    <xsl:template match="text()[not(parent::c or parent::reg[not(*)])][normalize-space(.) = '']"/>

    <!-- Long s (ſ) reads as a plain s in the base text column. -->
    <xsl:template match="text()">
        <xsl:value-of select="translate(., 'ſ', 's')"/>
    </xsl:template>

</xsl:stylesheet>
